"""Reproduce findings F2 (Added-date resets) and F6 (provable minimum age).

Reads only added_text_oct7_vs_current.csv in this folder, so it still works
after the Oct-7 database copy is gone.

  python docs/listing-trust-2026-10-10/evidence/reproduce.py [--now 2026-10-10T08:00]

Timestamps in the CSV are the crawler's naive local times; --now should be in
the same clock. Expect +/- 1 day of slack from time zones and Zameen's rounding.
"""
import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV = HERE / "added_text_oct7_vs_current.csv"

# Conservative minimum days for "N <unit> ago": the smallest age Zameen's label can mean.
MIN_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 28, "year": 365}
AGE_RE = re.compile(r"(\d+)\s*(minute|hour|day|week|month|year)s?")


def unit(text):
    t = (text or "").lower()
    for u in ("year", "month", "week", "day"):
        if u in t:
            return u
    if "hour" in t or "minute" in t:
        return "hour"
    return "other"


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "")[:26]) if value else None


def min_age_days(text, seen_at, now):
    """Smallest true age, in days, that an 'Added: N unit ago' label seen at seen_at proves."""
    if not text or not seen_at:
        return None
    t = text.lower()
    m = AGE_RE.search(t)
    if m:
        base = int(m.group(1)) * MIN_DAYS[m.group(2)]
    elif "yesterday" in t:
        base = 1
    else:
        return None
    return base + (now - seen_at).total_seconds() / 86400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default="2026-10-10T08:00")
    now = datetime.fromisoformat(ap.parse_args().now)

    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))

    # F2: resets that coarse rounding cannot explain, among listings re-scraped >= 2 days after Oct 7.
    reset_pairs = {("month", "day"), ("month", "hour"), ("week", "day"), ("week", "hour"),
                   ("day", "hour"), ("hour", "hour")}
    eligible = resets = 0
    crosstab = Counter()
    for r in rows:
        o_seen, n_seen = ts(r["oct7_card_scraped_at"]), ts(r["cur_card_scraped_at"])
        if not (r["oct7_added_text"] and r["cur_added_text"] and o_seen and n_seen):
            continue
        if (n_seen - o_seen).total_seconds() < 2 * 86400:
            continue
        eligible += 1
        pair = (unit(r["oct7_added_text"]), unit(r["cur_added_text"]))
        crosstab[pair] += 1
        resets += pair in reset_pairs
    print(f"F2: {resets} of {eligible} re-scraped listings reset ({100 * resets / eligible:.1f}%)")
    for pair, n in sorted(crosstab.items()):
        print(f"    {pair[0]:>6} -> {pair[1]:<6} {n}")

    # F6: provable minimum age per active listing, taking the larger lower bound of both observations.
    active = [r for r in rows if r["is_active"] == "1"]
    buckets = Counter()
    for r in active:
        bounds = [b for b in (
            min_age_days(r["cur_added_text"], ts(r["cur_card_scraped_at"]), now),
            min_age_days(r["oct7_added_text"], ts(r["oct7_card_scraped_at"]), now),
        ) if b is not None]
        if not bounds:
            buckets["unknown"] += 1
            continue
        best = max(bounds)
        for days in (7, 14, 30, 60):
            buckets[days] += best >= days
    total = len(active)
    print(f"F6: active listings {total}")
    for days in (7, 14, 30, 60):
        print(f"    provably >= {days:>2} days old: {buckets[days]} ({100 * buckets[days] / total:.1f}%)")
    if buckets["unknown"]:
        print(f"    no parseable Added label: {buckets['unknown']}")


if __name__ == "__main__":
    main()
