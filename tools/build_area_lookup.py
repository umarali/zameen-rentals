"""Build app/area_lookup.json from a crawled database's Zameen location paths.

    python3 tools/build_area_lookup.py data/rebuild/zameenrentals.db

For each city it writes, keyed by the names in app/areas_*.json:
- "urdu": Urdu name -> area, from Zameen's name_l1 (plus the spellings people
  type for Islamabad sectors, e.g. "ایف ۔ 8" also as "ایف 8" and "ایف ایٹ").
- "ancestors": area -> the known areas that contain it, from listing paths
  ("North Buffer Zone" -> ["North Karachi"]).

The database is opened read-only. The parser only reads the JSON output.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import CITIES, area_names_for_location_id, canonical_area_name  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "area_lookup.json"

# Islamabad sector numbers as people say them, written in Urdu script.
_SPOKEN_NUMBERS = {
    "5": "فائیو", "6": "سکس", "7": "سیون", "8": "ایٹ", "9": "نائن", "10": "ٹین",
    "11": "الیون", "12": "ٹویلو", "13": "تھرٹین", "14": "فورٹین", "15": "ففٹین",
    "16": "سکسٹین", "17": "سیونٹین",
}
_SECTOR_RE = re.compile(r"^(\S+)\s*[۔-]\s*(\d+)(?:/(\d+))?$")


def urdu_variants(name_l1):
    """The Urdu name plus the forms people type for 'X ۔ 8' sector names."""
    name = " ".join(name_l1.split())
    variants = {name}
    m = _SECTOR_RE.match(name)
    if m:
        letter, number, sub = m.groups()
        tail = f"/{sub}" if sub else ""
        variants |= {f"{letter} {number}{tail}", f"{letter}-{number}{tail}", f"{letter}{number}{tail}"}
        if not sub and number in _SPOKEN_NUMBERS:
            variants.add(f"{letter} {_SPOKEN_NUMBERS[number]}")
    return variants


def build(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    lookup = {}
    for city in CITIES:
        urdu, ancestors = {}, {}
        for location_id, name_l1 in conn.execute(
            "SELECT location_id, name_l1 FROM locations WHERE city = ? AND name_l1 IS NOT NULL "
            "ORDER BY level, location_id", (city,)
        ):
            area = canonical_area_name(city, location_id)
            if not area:
                continue
            for variant in sorted(urdu_variants(name_l1)):
                urdu.setdefault(variant, area)  # shallower levels win a shared name

        # Ancestors: in each listing path, every known area above a known area.
        paths = {}
        for zameen_id, location_id, level in conn.execute(
            "SELECT ll.zameen_id, ll.location_id, ll.level FROM listing_locations ll "
            "JOIN listings l USING (zameen_id) WHERE l.city = ?", (city,)
        ):
            paths.setdefault(zameen_id, []).append((level, location_id))
        for path in paths.values():
            known = [area_names_for_location_id(city, lid) and canonical_area_name(city, lid)
                     for _, lid in sorted(path)]
            known = [a for a in known if a and a != CITIES[city]["name"]]
            for i, area in enumerate(known):
                for parent in known[:i]:
                    if parent != area:
                        ancestors.setdefault(area, set()).add(parent)
        lookup[city] = {
            "urdu": dict(sorted(urdu.items())),
            "ancestors": {a: sorted(p) for a, p in sorted(ancestors.items())},
        }
    return lookup


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = build(sys.argv[1])
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    for city, d in data.items():
        print(f"{city}: {len(d['urdu'])} Urdu names, {len(d['ancestors'])} areas with ancestors")
