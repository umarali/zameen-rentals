"""Static checks for the public pricing, FAQ, privacy and terms pages.

The pages are plain HTML (they must render without JavaScript), so the numbers
in them are written out. These tests keep them in step with app/credits.py.
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from app import credits
from app.routes import _PUBLIC_PAGES

PUBLIC = Path(__file__).resolve().parents[1] / "frontend" / "public"
PAGES = ["about", "pricing", "faq", "privacy", "terms"]


class _Items(HTMLParser):
    """Collect data-* attributes of list items and the page's visible text."""

    def __init__(self):
        super().__init__()
        self.items, self.text, self._skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li" and any(k.startswith("data-") for k in attrs):
            self.items.append(attrs)
        if tag in ("script", "style", "head"):
            self._skip += 1
        if any(k == "data-starter-credits" for k in attrs):
            self.items.append(attrs)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)


def _parse(name):
    parser = _Items()
    parser.feed((PUBLIC / f"{name}.html").read_text())
    return parser


def test_public_pages_are_routed_and_in_the_sitemap():
    sitemap = (PUBLIC / "sitemap.xml").read_text()
    for name in PAGES:
        assert _PUBLIC_PAGES[name] == f"{name}.html"
        assert f"<loc>https://zameenrental.com/{name}</loc>" in sitemap


def test_pricing_matches_credits_module():
    parser = _parse("pricing")
    packs = {i["data-pack"]: i for i in parser.items if "data-pack" in i}
    assert set(packs) == set(credits.PACKS)
    for pack_id, pack in credits.PACKS.items():
        assert int(packs[pack_id]["data-credits"]) == pack["credits"]
        assert int(packs[pack_id]["data-price-pkr"]) == pack["price_pkr"]
    actions = {i["data-action"]: int(i["data-cost"]) for i in parser.items if "data-action" in i}
    assert actions, "pricing lists no paid actions"
    for action, cost in actions.items():
        assert credits.COSTS[action] == cost
    starter = [i for i in parser.items if "data-starter-credits" in i]
    assert [int(s["data-starter-credits"]) for s in starter] == [credits.STARTER_CREDITS]
    text = " ".join(parser.text)
    for pack in credits.PACKS.values():
        assert f"{pack['credits']} credits" in text and f"Rs {pack['price_pkr']}" in text
    assert f"{credits.STARTER_CREDITS} free credits" in text


def test_faq_starter_credits_and_schema_match():
    html = (PUBLIC / "faq.html").read_text()
    assert f"New visitors get {credits.STARTER_CREDITS} free credits" in html
    schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    visible = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", html, re.S)
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    assert [(q["name"], q["acceptedAnswer"]["text"]) for q in schema["mainEntity"]] == [
        (strip(q), strip(a)) for q, a in visible
    ]


def test_owner_notes_stay_in_comments():
    for name in PAGES:
        text = " ".join(_parse(name).text)
        assert "DECISION" not in text and "CHECK:" not in text, name
        assert not re.search(r"\[(OPERATOR NAME|CONTACT EMAIL|LOG RETENTION PERIOD)\]|registered company|Claude|AI model", text), name
        html = (PUBLIC / f"{name}.html").read_text()
        assert f'<link rel="canonical" href="https://zameenrental.com/{name}">' in html
        assert 'href="/privacy"' in html and 'href="/terms"' in html, name
