"""
Decide, per tag, whether Jev, Claude Haiku or plain keywords should power it.

A tag ships only if the 95% Wilson lower bound on its precision is at least
0.90. When keywords pass too, keywords win (open source) unless a model
finds clearly more true tags.

Usage:
  # 1. Stratified sample of listings with descriptions, for hand labelling
  python tools/eval_listing_tags.py sample --n 350 --out labels.csv
  # 2. A person fills tenant_fit (family/bachelor/either/unclear) and the y/n columns
  # 3. Predictions (cached; reruns skip listings already predicted)
  python tools/eval_listing_tags.py predict jev labels.csv --out preds_jev.jsonl
  python tools/eval_listing_tags.py predict haiku labels.csv --out preds_haiku.jsonl
  # 4. Report
  python tools/eval_listing_tags.py score labels.csv --pred jev=preds_jev.jsonl --pred haiku=preds_haiku.jsonl

`sample` reads the database (ZAMEENRENTALS_DB_DIR); `predict` and `score`
only read the CSV, so labels can be scored anywhere.

Sampling: each listing falls in the stratum of the rarest tag its keywords
hit, or "none". Hit strata are oversampled so rare tags appear at all; every
estimate is weighted back by stratum population.
"""
import argparse
import asyncio
import csv
import json
import math
import random
import re
import sys
import time
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.decisions import DecisionError, jev_from_env  # noqa: E402
from app.listing_tags import FEATURES, QUESTIONS, TENANT_FITS, listing_state, public_tags  # noqa: E402

LABEL_COLUMNS = ["tenant_fit", *FEATURES]
TAG_KEYS = ["bachelor_ok", "family_ok", *FEATURES]
CONTEXT_COLUMNS = ["city", "area_name", "property_type", "price", "bedrooms", "area_size",
                   "amenities_json", "title", "description"]
PRECISION_BAR = 0.90
CLEAR_RECALL_GAIN = 0.10   # a model must find this much more to beat passing keywords
HAIKU_MODEL = "claude-haiku-4-5"

# ── Keyword baseline (open source; also defines the sampling strata) ──

_KEYWORDS = {
    "backup_power": re.compile(r"\b(solar|ups|inverter|generator|backup)\b", re.I),
    "separate_entrance": re.compile(r"\b(separate|independent|own)\s+(gate|entrance|entry|door)\b", re.I),
    "newly_built": re.compile(r"\b(brand\s*new|newly\s+(built|constructed)|never\s+(lived|used))\b", re.I),
}
_BACHELOR = re.compile(r"\b(bachelors?|students?|working\s+(men|women|ladies)|boys|girls)\b", re.I)
_NO_BACHELOR = re.compile(r"\bno\s+bachelors?\b", re.I)
_FAMILY_ONLY = re.compile(r"\b((only|just)\s+(for\s+)?famil(y|ies)|famil(y|ies)\s+only|no\s+bachelors?)\b", re.I)
# Rarest first: a listing is sampled under the rarest tag its keywords hit.
STRATA = ["tenant", "separate_entrance", "backup_power", "newly_built", "none"]


def keyword_tags(text):
    tags = {name: True if rx.search(text) else None for name, rx in _KEYWORDS.items()}
    family = bool(_FAMILY_ONLY.search(text))
    bachelor = bool(_BACHELOR.search(text)) and not _NO_BACHELOR.search(text)
    tags["tenant_fit"] = ("either" if family and bachelor else "family" if family
                          else "bachelor" if bachelor else None)
    return tags


def stratum_of(text):
    tags = keyword_tags(text)
    if tags["tenant_fit"]:
        return "tenant"
    for name in ("separate_entrance", "backup_power", "newly_built"):
        if tags[name]:
            return name
    return "none"


def _text(row):
    return f"{row['title'] or ''}\n{row['description'] or ''}"


# ── sample ──

def allocate(populations, n, none_share=1 / 3):
    """Sample sizes per stratum: a fixed share for "none", the rest split evenly over hits."""
    sizes = {s: 0 for s in populations}
    hit_strata = [s for s in STRATA if s != "none" and populations.get(s)]
    budget = n - min(populations.get("none", 0), round(n * none_share))
    for i, s in enumerate(hit_strata):
        share = budget // (len(hit_strata) - i)
        sizes[s] = min(populations[s], share)
        budget -= sizes[s]
    sizes["none"] = min(populations.get("none", 0), n - sum(sizes.values()))
    return sizes


def sample(args):
    from app.database import _get_conn, close_db
    where = "is_active = 1 AND COALESCE(title, '') != ''"
    if not args.include_title_only:
        where += " AND COALESCE(description, '') != ''"
    rows = _get_conn().execute(f"SELECT * FROM listings WHERE {where}").fetchall()
    by_stratum = {s: [] for s in STRATA}
    for r in rows:
        by_stratum[stratum_of(_text(r))].append(r)
    populations = {s: len(v) for s, v in by_stratum.items()}
    sizes = allocate(populations, args.n)
    rng = random.Random(args.seed)
    picked = [(s, r) for s in STRATA for r in rng.sample(by_stratum[s], sizes[s])]
    rng.shuffle(picked)  # so labellers don't see strata in blocks
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["zameen_id", "stratum", "stratum_population", *CONTEXT_COLUMNS, *LABEL_COLUMNS])
        for s, r in picked:
            writer.writerow([r["zameen_id"], s, populations[s], *[r[c] for c in CONTEXT_COLUMNS],
                             *[""] * len(LABEL_COLUMNS)])
    close_db()
    print(f"{len(rows)} eligible listings; wrote {len(picked)} rows to {args.out}")
    for s in STRATA:
        print(f"  {s:<18} population {populations[s]:>6}  sampled {sizes[s]:>4}")


# ── predict ──

def _context_row(label_row):
    """A CSV row shaped like a listings row, for listing_state()."""
    row = {c: (label_row.get(c) or None) for c in CONTEXT_COLUMNS}
    for c in ("price", "bedrooms"):
        row[c] = int(float(row[c])) if row[c] else None
    return row


async def predict_jev(rows, provider, concurrency=4):
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            started = time.perf_counter()
            decision = await provider.decide(listing_state(_context_row(row)), QUESTIONS)
            a = decision.answers
            return {
                "zameen_id": row["zameen_id"],
                "tenant_fit": a["tenant_fit"].value,
                "tenant_fit_confidence": a["tenant_fit"].confidence,
                **{name: a[name].value for name in FEATURES},
                "model": decision.model,
                "input_tokens": decision.input_tokens,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }

    return await asyncio.gather(*(one(r) for r in rows))


def _haiku_system():
    lines = ["You tag Pakistani rental listings. Answer only from what the listing states."]
    tenant = QUESTIONS["tenant_fit"]
    lines.append(f"tenant_fit: {tenant['instructions']}")
    lines += [f"  - {k}: {v}" for k, v in tenant["criteria"].items()]
    for name in FEATURES:
        lines.append(f"{name}: true only if this holds: {QUESTIONS[name]['instructions']}")
    return "\n".join(lines)


def haiku_record(zameen_id, parsed, usage, latency_ms):
    """Haiku gives labels, not probabilities: score them as fully confident answers."""
    return {
        "zameen_id": zameen_id,
        "tenant_fit": parsed.tenant_fit,
        "tenant_fit_confidence": 1.0,
        **{name: 1.0 if getattr(parsed, name) else 0.0 for name in FEATURES},
        "model": HAIKU_MODEL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "latency_ms": latency_ms,
    }


async def predict_haiku(rows, client, concurrency=4):
    from pydantic import BaseModel

    class HaikuTags(BaseModel):
        tenant_fit: Literal[TENANT_FITS]
        backup_power: bool
        separate_entrance: bool
        newly_built: bool

    system = _haiku_system()
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            started = time.perf_counter()
            response = await client.messages.parse(
                model=HAIKU_MODEL,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": listing_state(_context_row(row))}],
                output_format=HaikuTags,
            )
            return haiku_record(row["zameen_id"], response.parsed_output, response.usage,
                                (time.perf_counter() - started) * 1000)

    return await asyncio.gather(*(one(r) for r in rows))


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _read_preds(path):
    if not Path(path).exists():
        return {}
    with open(path) as f:
        return {p["zameen_id"]: p for p in (json.loads(line) for line in f if line.strip())}


async def predict(args):
    rows = _read_csv(args.labels)
    done = _read_preds(args.out)
    todo = [r for r in rows if r["zameen_id"] not in done]
    if args.model == "jev":
        provider = jev_from_env()
        if provider is None:
            sys.exit("TYPESAFE_API_KEY is not set")
        try:
            records = await predict_jev(todo, provider, args.concurrency)
        except DecisionError as exc:
            sys.exit(f"Jev failed: {exc}")
        finally:
            await provider.aclose()
    else:
        import anthropic
        async with anthropic.AsyncAnthropic() as client:
            records = await predict_haiku(todo, client, args.concurrency)
    with open(args.out, "a") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    _print_usage(args.model, list(done.values()) + records)


def _print_usage(name, records):
    if not records:
        print(f"{name}: no predictions")
        return
    lat = sorted(r["latency_ms"] for r in records)
    tokens_in = sum(r.get("input_tokens", 0) for r in records)
    tokens_out = sum(r.get("output_tokens", 0) for r in records)
    usd = (tokens_in * 0.042 / 1e6 if name == "jev"
           else tokens_in * 1.0 / 1e6 + tokens_out * 5.0 / 1e6)  # Haiku 4.5: $1 / $5 per MTok
    p95 = lat[max(0, math.ceil(len(lat) * 0.95) - 1)]
    print(f"{name}: {len(records)} predictions, {tokens_in:,} in / {tokens_out:,} out tokens, "
          f"${usd:.4f} (${usd / len(records) * 1000:.3f} per 1k listings), "
          f"latency p50 {lat[len(lat) // 2]:.0f}ms p95 {p95:.0f}ms")


# ── score ──

def wilson_lower(p, n, z=1.96):
    if n <= 0:
        return None
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def weighted_metrics(items):
    """items: (predicted, gold, weight). Weighted precision with Wilson bound, recall, accuracy."""
    pos = [(g, w) for p, g, w in items if p]
    sw = sum(w for _, w in pos)
    precision = sum(w for g, w in pos if g) / sw if sw else None
    n_eff = sw * sw / sum(w * w for _, w in pos) if pos else 0
    gold_w = sum(w for _, g, w in items if g)
    recall = sum(w for p, g, w in items if p and g) / gold_w if gold_w else None
    total_w = sum(w for *_, w in items)
    accuracy = sum(w for p, g, w in items if bool(p) == bool(g)) / total_w if total_w else None
    return {
        "predicted": len(pos),
        "gold": sum(1 for _, g, _ in items if g),
        "precision": precision,
        "precision_lb": wilson_lower(precision, n_eff) if precision is not None else None,
        "recall": recall,
        "accuracy": accuracy,
    }


def _yes(value):
    return (value or "").strip().lower() in ("y", "yes", "1", "true")


def _tag_values(tags):
    tenant = tags["tenant_fit"]
    return {
        "bachelor_ok": tenant in ("bachelor", "either"),
        "family_ok": tenant in ("family", "either"),
        **{name: bool(tags[name]) for name in FEATURES},
    }


def gold_values(label):
    tenant = (label["tenant_fit"] or "").strip().lower()
    return {
        "bachelor_ok": tenant in ("bachelor", "either"),
        "family_ok": tenant in ("family", "either"),
        **{name: _yes(label[name]) for name in FEATURES},
    }


def verdict(results):
    """results: {system: metrics} for one tag. Returns the system to ship, and why."""
    passing = {s: m for s, m in results.items()
               if m["precision_lb"] is not None and m["precision_lb"] >= PRECISION_BAR}
    if not passing:
        return "none", f"no system reaches precision lower bound {PRECISION_BAR:.2f}"
    if "keywords" in passing:
        kw_recall = passing["keywords"]["recall"] or 0
        better = {s: m for s, m in passing.items()
                  if s != "keywords" and (m["recall"] or 0) >= kw_recall + CLEAR_RECALL_GAIN}
        if not better:
            return "keywords", "passes, and no model finds clearly more"
        best = max(better, key=lambda s: better[s]["recall"])
        return best, f"recall {better[best]['recall']:.2f} vs keywords {kw_recall:.2f}"
    best = max(passing, key=lambda s: passing[s]["recall"] or 0)
    return best, "only passing system" if len(passing) == 1 else "highest recall of passing systems"


def score_rows(labels, preds_by_system):
    """Per tag, per system metrics. labels: CSV dicts; preds_by_system: {name: {zameen_id: record}}."""
    labelled = [r for r in labels if any((r[c] or "").strip() for c in LABEL_COLUMNS)]
    per_stratum = {}
    for r in labelled:
        per_stratum[r["stratum"]] = per_stratum.get(r["stratum"], 0) + 1
    weight = {s: int(next(r["stratum_population"] for r in labelled if r["stratum"] == s)) / n
              for s, n in per_stratum.items()}
    # Only rows every system predicted, so all columns score the same listings.
    common = [r for r in labelled
              if all(r["zameen_id"] in preds for preds in preds_by_system.values())]
    systems = {"keywords": lambda r: _tag_values(keyword_tags(_text(r)))}
    for name, preds in preds_by_system.items():
        systems[name] = lambda r, preds=preds: _tag_values(public_tags(preds[r["zameen_id"]]))
    table = {}
    for key in TAG_KEYS:
        table[key] = {}
        for name, predict_fn in systems.items():
            items = [(predict_fn(r)[key], gold_values(r)[key], weight[r["stratum"]]) for r in common]
            table[key][name] = weighted_metrics(items)
    return table, len(labelled), len(common)


def _fmt(x):
    return "  -  " if x is None else f"{x:5.2f}"


def score(args):
    labels = _read_csv(args.labels)
    preds = {}
    for spec in args.pred or []:
        name, _, path = spec.partition("=")
        preds[name] = _read_preds(path)
        _print_usage(name, list(preds[name].values()))
    table, n_labelled, n_common = score_rows(labels, preds)
    print(f"\n{n_labelled} labelled rows, {n_common} predicted by every system. "
          f"Estimates are weighted by stratum population.\n")
    print(f"{'tag':<18} {'system':<9} {'pred+':>5} {'gold+':>5}  {'prec':>5} {'lb95':>5} {'recall':>6} {'acc':>5}")
    for key, by_system in table.items():
        for name, m in by_system.items():
            print(f"{key:<18} {name:<9} {m['predicted']:>5} {m['gold']:>5}  {_fmt(m['precision'])} "
                  f"{_fmt(m['precision_lb'])} {_fmt(m['recall']):>6} {_fmt(m['accuracy'])}")
        winner, why = verdict(by_system)
        print(f"{'':<18} → ship on {winner}: {why}\n")
    print(f"pred+ = listings the system tags; gold+ = listings a person tagged.\n"
          f"lb95 = 95% Wilson lower bound on precision; a tag needs lb95 ≥ {PRECISION_BAR:.2f}.\n"
          f"Few pred+ rows means a wide interval; label more of that stratum before trusting it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=350)
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--include-title-only", action="store_true")
    p = sub.add_parser("predict")
    p.add_argument("model", choices=["jev", "haiku"])
    p.add_argument("labels")
    p.add_argument("--out", required=True)
    p.add_argument("--concurrency", type=int, default=4)
    sc = sub.add_parser("score")
    sc.add_argument("labels")
    sc.add_argument("--pred", action="append", metavar="NAME=PATH")
    args = parser.parse_args()
    if args.cmd == "sample":
        sample(args)
    elif args.cmd == "predict":
        asyncio.run(predict(args))
    else:
        score(args)


if __name__ == "__main__":
    main()
