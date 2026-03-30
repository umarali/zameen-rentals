"""
Deep area discovery from Zameen.com — works for any city.
Crawls the main city page + property type pages + sub-areas.

Usage:
  python tools/deep_discover.py                    # Karachi (default)
  python tools/deep_discover.py --city lahore
  python tools/deep_discover.py --city islamabad
"""
import argparse
import re
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup
from app.data import CITIES

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def build_area_regex(city_name):
    """Build regex to match area URLs for a given city."""
    return re.compile(
        rf'/(Rentals(?:_[^/]*)?/({city_name}[^"\'?\s#]*?)-(\d+)-\d+\.html)'
    )


def extract_areas_from_html(html, city_name):
    """Extract all area slugs/IDs from a page's HTML."""
    area_re = build_area_regex(city_name)
    soup = BeautifulSoup(html, "html.parser")
    areas = {}

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = area_re.search(href)
        if not m:
            continue
        slug = m.group(2)
        area_id = int(m.group(3))
        name = slug.replace(f"{city_name}_", "").replace("_", " ")
        if name == city_name or slug == city_name:
            continue
        if slug not in areas:
            areas[slug] = (name, area_id)

    for script in soup.select("script"):
        text = script.string or ""
        for m in area_re.finditer(text):
            slug = m.group(2)
            area_id = int(m.group(3))
            name = slug.replace(f"{city_name}_", "").replace("_", " ")
            if name == city_name or slug == city_name:
                continue
            if slug not in areas:
                areas[slug] = (name, area_id)

    return areas


def fetch(url):
    """Fetch a URL with retry."""
    for attempt in range(3):
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                time.sleep(3 + attempt * 2)
            else:
                print(f"  HTTP {resp.status_code} for {url}")
                return None
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(2)
    return None


def discover_all(city_key):
    """Deep crawl to find all areas for a city."""
    city_info = CITIES.get(city_key)
    if not city_info:
        print(f"Unknown city: {city_key}. Available: {list(CITIES.keys())}")
        sys.exit(1)

    city_name = city_info["name"]
    city_id = city_info["id"]
    all_areas = {}

    # Phase 1: Main city rentals page
    print(f"Phase 1: Fetching main {city_name} page...")
    html = fetch(f"https://www.zameen.com/Rentals/{city_name}-{city_id}-1.html")
    if html:
        found = extract_areas_from_html(html, city_name)
        all_areas.update(found)
        print(f"  Found {len(found)} areas from main page")

    # Phase 2: Property type pages (they sometimes reveal different areas)
    type_slugs = [
        "Rentals_Houses_Property",
        "Rentals_Flats_Apartments",
        "Rentals_Upper_Portions",
        "Rentals_Lower_Portions",
    ]
    for slug in type_slugs:
        print(f"Phase 2: Fetching {slug} page...")
        html = fetch(f"https://www.zameen.com/{slug}/{city_name}-{city_id}-1.html")
        if html:
            found = extract_areas_from_html(html, city_name)
            new = {k: v for k, v in found.items() if k not in all_areas}
            all_areas.update(new)
            print(f"  Found {len(new)} new areas")
        time.sleep(1)

    # Phase 3: Deep crawl - visit each discovered area to find sub-areas
    print(f"\nPhase 3: Deep crawl {len(all_areas)} areas for sub-areas...")
    parent_slugs = list(all_areas.items())
    for i, (slug, (name, area_id)) in enumerate(parent_slugs):
        url = f"https://www.zameen.com/Rentals/{slug}-{area_id}-1.html"
        print(f"  [{i+1}/{len(parent_slugs)}] Crawling: {name}...")
        html = fetch(url)
        if html:
            found = extract_areas_from_html(html, city_name)
            new = {k: v for k, v in found.items() if k not in all_areas}
            if new:
                all_areas.update(new)
                print(f"    Found {len(new)} new sub-areas: {', '.join(v[0] for v in new.values())}")
        time.sleep(0.5)

    return all_areas


def main():
    parser = argparse.ArgumentParser(description="Discover Zameen.com areas for a city")
    parser.add_argument("--city", default="karachi", choices=list(CITIES.keys()),
                        help="City to discover areas for (default: karachi)")
    args = parser.parse_args()

    city_key = args.city
    city_name = CITIES[city_key]["name"]
    all_areas = discover_all(city_key)

    print(f"\n{'='*60}")
    print(f"Total areas discovered for {city_name}: {len(all_areas)}")
    print(f"{'='*60}\n")

    # Compare with current area file
    area_file = Path(__file__).resolve().parent.parent / "app" / CITIES[city_key]["file"]
    current_slugs = set()
    if area_file.exists():
        with open(area_file) as f:
            current = json.load(f)
        current_slugs = {info["slug"] for info in current.values()}

    new_areas = {slug: info for slug, info in all_areas.items() if slug not in current_slugs}
    existing = {slug: info for slug, info in all_areas.items() if slug in current_slugs}

    print(f"Already in {CITIES[city_key]['file']}: {len(existing)}")
    print(f"NEW areas to add: {len(new_areas)}")

    if new_areas:
        print(f"\n--- NEW AREAS ---\n")
        for slug, (name, area_id) in sorted(new_areas.items(), key=lambda x: x[1][0]):
            print(f'    "{name}": {{"slug": "{slug}", "id": {area_id}}}')

    # Output complete JSON
    output = {}
    for slug, (name, area_id) in sorted(all_areas.items(), key=lambda x: x[1][0]):
        output[name] = {"slug": slug, "id": area_id}

    out_path = Path(__file__).parent / f"discovered_{city_key}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
