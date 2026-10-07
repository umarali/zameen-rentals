"""
Check Jev listing tags against hand labels, next to a keyword baseline.
If the keywords score as well as Jev on a tag, that tag doesn't need Jev.

Usage:
  python tools/eval_listing_tags.py sample --n 150 --out labels.csv
      # fill tenant_fit (family/bachelor/either/unclear) and the y/n columns by hand
  python tools/tag_listings.py --limit 100000   # make sure the sample is tagged
  python tools/eval_listing_tags.py score labels.csv
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import _get_conn, close_db  # noqa: E402
from app.listing_tags import FEATURES, init_listing_tags_schema, public_tags  # noqa: E402

LABEL_COLUMNS = ["tenant_fit", *FEATURES]

_KEYWORDS = {
    "backup_power": re.compile(r"\b(solar|ups|inverter|generator|backup)\b", re.I),
    "separate_entrance": re.compile(r"\b(separate|independent|own)\s+(gate|entrance|entry|door)\b", re.I),
    "newly_built": re.compile(r"\b(brand\s*new|newly\s+(built|constructed)|never\s+(lived|used))\b", re.I),
}
_BACHELOR = re.compile(r"\b(bachelors?|students?|working\s+(men|women|ladies)|boys|girls)\b", re.I)
_FAMILY_ONLY = re.compile(r"\b((only|just)\s+(for\s+)?famil(y|ies)|famil(y|ies)\s+only|no\s+bachelors?)\b", re.I)
_ANY_KEYWORD = re.compile("|".join(
    [p.pattern for p in _KEYWORDS.values()] + [_BACHELOR.pattern, _FAMILY_ONLY.pattern]), re.I)


def keyword_tags(text):
    tags = {name: True if rx.search(text) else None for name, rx in _KEYWORDS.items()}
    family = bool(_FAMILY_ONLY.search(text))
    bachelor = bool(_BACHELOR.search(text)) and not re.search(r"\bno\s+bachelors?\b", text, re.I)
    tags["tenant_fit"] = ("either" if family and bachelor else "family" if family
                          else "bachelor" if bachelor else None)
    return tags


def _text(row):
    return f"{row['title'] or ''}\n{row['description'] or ''}"


def sample(args):
    where = "is_active = 1 AND COALESCE(title, '') != ''"
    if not args.include_title_only:
        where += " AND COALESCE(description, '') != ''"
    rows = _get_conn().execute(
        f"SELECT * FROM listings WHERE {where} ORDER BY random() LIMIT ?", (args.n * 20,)
    ).fetchall()
    # Half with a keyword hit, half without, so rare tags show up at all.
    hits = [r for r in rows if _ANY_KEYWORD.search(_text(r))][: args.n // 2]
    misses = [r for r in rows if not _ANY_KEYWORD.search(_text(r))][: args.n - len(hits)]
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["zameen_id", "city", "title", "description", *LABEL_COLUMNS])
        for r in hits + misses:
            desc = " ".join((r["description"] or "").split())[:600]
            writer.writerow([r["zameen_id"], r["city"], r["title"], desc, *[""] * len(LABEL_COLUMNS)])
    print(f"wrote {len(hits) + len(misses)} rows to {args.out} ({len(hits)} keyword hits)")


def _yes(value):
    return value.strip().lower() in ("y", "yes", "1", "true")


def _filter_matches(tenant_value, wanted):
    return tenant_value in (wanted, "either")


def _pr(pairs):
    """Precision and recall of predicted-True against labelled-True."""
    tp = sum(1 for pred, gold in pairs if pred and gold)
    fp = sum(1 for pred, gold in pairs if pred and not gold)
    fn = sum(1 for pred, gold in pairs if not pred and gold)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return precision, recall, tp + fn


def _fmt(x):
    return "  n/a" if x is None else f"{x:5.2f}"


def score(args):
    conn = _get_conn()
    with open(args.labels, newline="") as f:
        labelled = [r for r in csv.DictReader(f) if any(r[c].strip() for c in LABEL_COLUMNS)]
    jev_pairs = {k: [] for k in ("bachelor_ok", "family_ok", *FEATURES)}
    kw_pairs = {k: [] for k in jev_pairs}
    untagged = 0
    for label in labelled:
        listing = conn.execute("SELECT * FROM listings WHERE zameen_id = ?",
                               (label["zameen_id"],)).fetchone()
        tag_row = conn.execute("SELECT * FROM listing_tags WHERE zameen_id = ?",
                               (label["zameen_id"],)).fetchone()
        if listing is None or tag_row is None:
            untagged += 1
            continue
        jev = public_tags(tag_row)
        kw = keyword_tags(_text(listing))
        gold_tenant = label["tenant_fit"].strip().lower()
        for key, wanted in (("bachelor_ok", "bachelor"), ("family_ok", "family")):
            gold = _filter_matches(gold_tenant, wanted)
            jev_pairs[key].append((_filter_matches(jev["tenant_fit"], wanted), gold))
            kw_pairs[key].append((_filter_matches(kw["tenant_fit"], wanted), gold))
        for name in FEATURES:
            gold = _yes(label[name])
            jev_pairs[name].append((bool(jev[name]), gold))
            kw_pairs[name].append((bool(kw[name]), gold))

    print(f"{len(labelled)} labelled rows, {untagged} skipped (not tagged yet)\n")
    print(f"{'tag':<18} {'positives':>9}   {'Jev P':>5} {'Jev R':>5}   {'kw P':>5} {'kw R':>5}")
    for key in jev_pairs:
        jp, jr, positives = _pr(jev_pairs[key])
        kp, kr, _ = _pr(kw_pairs[key])
        print(f"{key:<18} {positives:>9}   {_fmt(jp)} {_fmt(jr)}   {_fmt(kp)} {_fmt(kr)}")
    print("\nP = precision (shown tags that are right), R = recall (true tags we show).")
    print("Ship a filter chip only where precision is high; recall is coverage.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=150)
    s.add_argument("--out", required=True)
    s.add_argument("--include-title-only", action="store_true")
    sc = sub.add_parser("score")
    sc.add_argument("labels")
    args = parser.parse_args()
    init_listing_tags_schema()
    try:
        sample(args) if args.cmd == "sample" else score(args)
    finally:
        close_db()


if __name__ == "__main__":
    main()
