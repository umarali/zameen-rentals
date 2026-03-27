"""
One-time utility to discover Karachi area slugs/IDs from Zameen.com.
Run: python discover_areas.py
Not deployed — outputs a dict literal you can paste into main.py.
"""
import re
import httpx
from bs4 import BeautifulSoup

URL = "https://www.zameen.com/Rentals/Karachi-2-1.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Pattern: /Rentals/Karachi_{SLUG}-{ID}-1.html  OR  /Rentals/{SLUG}-{ID}-1.html
AREA_RE = re.compile(r'/Rentals/(Karachi[^"]*?)-(\d+)-1\.html')


def discover():
    print(f"Fetching {URL} ...")
    resp = httpx.get(URL, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    areas = {}
    # Look for area links in sidebar, filters, breadcrumbs, and all anchor tags
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = AREA_RE.search(href)
        if not m:
            continue
        slug = m.group(1)
        area_id = int(m.group(2))
        # Derive human-readable name from slug
        name = slug.replace("Karachi_", "").replace("_", " ")
        # Skip the generic "Karachi" entry
        if name == "Karachi" or slug == "Karachi":
            continue
        if slug not in {v for v, _ in areas.values()}:
            areas[name] = (slug, area_id)

    # Also try to parse from script tags (Zameen sometimes embeds area lists as JSON)
    for script in soup.select("script"):
        text = script.string or ""
        for m in AREA_RE.finditer(text):
            slug = m.group(1)
            area_id = int(m.group(2))
            name = slug.replace("Karachi_", "").replace("_", " ")
            if name == "Karachi" or slug == "Karachi":
                continue
            if slug not in {v[0] for v in areas.values()}:
                areas[name] = (slug, area_id)

    return areas


def main():
    areas = discover()
    if not areas:
        print("No areas discovered. Zameen.com may have changed their HTML structure.")
        print("Try inspecting the page manually.")
        return

    print(f"\nDiscovered {len(areas)} areas:\n")
    print("KARACHI_AREAS = {")
    for name, (slug, area_id) in sorted(areas.items()):
        print(f'    "{name}": ("{slug}", {area_id}, 0.0, 0.0),  # TODO: add lat/lng')
    print("}")

    # Also output just the new ones (not in current main.py)
    from main import KARACHI_AREAS as current
    current_slugs = {v[0] for v in current.values()}
    new = {n: v for n, v in areas.items() if v[0] not in current_slugs}
    if new:
        print(f"\n--- {len(new)} NEW areas not in main.py ---\n")
        for name, (slug, area_id) in sorted(new.items()):
            print(f'    "{name}": ("{slug}", {area_id}, 0.0, 0.0),')
    else:
        print("\nNo new areas found beyond what's already in main.py.")


if __name__ == "__main__":
    main()
