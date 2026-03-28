"""
Deep area discovery from Zameen.com.
Crawls the main Karachi page + each area's sub-page to find ALL areas.
Run: python tools/deep_discover.py
"""
import re
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Match any Zameen rental area URL for Karachi
AREA_RE = re.compile(r'/(Rentals(?:_[^/]*)?/(Karachi[^"\'?\s#]*?)-(\d+)-\d+\.html)')


def extract_areas_from_html(html):
    """Extract all area slugs/IDs from a page's HTML."""
    soup = BeautifulSoup(html, "html.parser")
    areas = {}

    # From all anchor tags
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = AREA_RE.search(href)
        if not m:
            continue
        slug = m.group(2)
        area_id = int(m.group(3))
        name = slug.replace("Karachi_", "").replace("_", " ")
        if name == "Karachi" or slug == "Karachi":
            continue
        if slug not in areas:
            areas[slug] = (name, area_id)

    # From script tags (Zameen sometimes embeds area data in JS)
    for script in soup.select("script"):
        text = script.string or ""
        for m in AREA_RE.finditer(text):
            slug = m.group(2)
            area_id = int(m.group(3))
            name = slug.replace("Karachi_", "").replace("_", " ")
            if name == "Karachi" or slug == "Karachi":
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


def discover_all():
    """Deep crawl to find all Karachi areas."""
    all_areas = {}

    # Phase 1: Main Karachi rentals page
    print("Phase 1: Fetching main Karachi page...")
    html = fetch("https://www.zameen.com/Rentals/Karachi-2-1.html")
    if html:
        found = extract_areas_from_html(html)
        all_areas.update(found)
        print(f"  Found {len(found)} areas from main page")

    # Phase 2: Try different property types (they sometimes show different areas)
    type_slugs = [
        "Rentals_Houses_Property",
        "Rentals_Flats_Apartments",
        "Rentals_Upper_Portions",
        "Rentals_Lower_Portions",
    ]
    for slug in type_slugs:
        print(f"Phase 2: Fetching {slug} page...")
        html = fetch(f"https://www.zameen.com/{slug}/Karachi-2-1.html")
        if html:
            found = extract_areas_from_html(html)
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
            found = extract_areas_from_html(html)
            new = {k: v for k, v in found.items() if k not in all_areas}
            if new:
                all_areas.update(new)
                print(f"    Found {len(new)} new sub-areas: {', '.join(v[0] for v in new.values())}")
        time.sleep(0.5)  # Be respectful

    return all_areas


def main():
    all_areas = discover_all()

    print(f"\n{'='*60}")
    print(f"Total areas discovered: {len(all_areas)}")
    print(f"{'='*60}\n")

    # Compare with current data.py
    from app.data import KARACHI_AREAS as current
    current_slugs = {v[0] for v in current.values()}

    new_areas = {slug: info for slug, info in all_areas.items() if slug not in current_slugs}
    existing = {slug: info for slug, info in all_areas.items() if slug in current_slugs}

    print(f"Already in data.py: {len(existing)}")
    print(f"NEW areas to add: {len(new_areas)}")

    if new_areas:
        print(f"\n--- NEW AREAS ---\n")
        for slug, (name, area_id) in sorted(new_areas.items(), key=lambda x: x[1][0]):
            print(f'    "{name}": ("{slug}", {area_id}, 0.0, 0.0),')

    # Output complete JSON for easy processing
    output = {}
    for slug, (name, area_id) in sorted(all_areas.items(), key=lambda x: x[1][0]):
        output[name] = {"slug": slug, "id": area_id}

    out_path = Path(__file__).parent / "discovered_areas.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
