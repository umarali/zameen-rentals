#!/usr/bin/env python3
"""Score the natural-language parser against hand-labelled queries.

    python3 tools/eval_nl_parser.py tests/fixtures/nl_eval_queries.jsonl \
        --configs regex,haiku45-full,haiku55-full,haiku55-candidates --out /tmp/nl-eval

Each line of the set: {"id", "city", "lang", "q", "expect": {field: value or
null}, "area_any": [...], "approx_ok": bool}. Only the fields in "expect" are
scored; null means the field must be absent. Queries run through the same
code as /api/parse-query (parser plus _build_parse_query_response), uncached,
against a throwaway database. AI configs call the Claude API and cost money:
roughly $0.15 per 150 queries on Haiku 5.5 with candidates, about $1 on
Haiku 4.5 with the full area list.

The metric that matters most is "silent wrong area": a wrong area the user
isn't warned about. A wrong area flagged area_approximate is shown to the user
as "No exact match", so it's counted separately.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ZAMEENRENTALS_DB_DIR", tempfile.mkdtemp(prefix="nl-eval-"))
os.environ["ZR_NL_DAILY_BUDGET_USD"] = "1000"  # the eval sets its own spend; never fall back mid-run

from dotenv import load_dotenv  # noqa: E402

if "--env" in sys.argv:
    load_dotenv(sys.argv[sys.argv.index("--env") + 1], override=True)
else:
    load_dotenv()

import app.parsing as parsing  # noqa: E402
from app.database import init_db  # noqa: E402
from app.routes import _build_parse_query_response  # noqa: E402

CONFIGS = {
    "regex": None,
    "haiku45-full": ("claude-haiku-4-5", "full"),
    "haiku55-full": ("claude-haiku-5-5", "full"),
    "haiku55-candidates": ("claude-haiku-5-5", "candidates"),
}
FIELDS = ["area", "areas", "property_type", "bedrooms", "bedrooms_max", "price_min", "price_max",
          "size_marla_min", "size_marla_max", "furnished", "sort"]


def load_set(path):
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    for c in cases:
        unknown = set(c["expect"]) - set(FIELDS)
        if unknown:
            raise SystemExit(f"{c['id']}: unknown expect fields {sorted(unknown)}")
    return cases


def _equal(field, got, want):
    if field.startswith("size_marla") and got is not None and want is not None:
        return abs(float(got) - float(want)) < 1e-6
    if field == "areas" and got is not None and want is not None:
        return list(got) == list(want)
    return got == want


def _area_id(name, city):
    from app.data import get_areas
    info = get_areas(city).get(name) if name else None
    return info[1] if info else None


def _same_area(a, b, city):
    """Equal names, or two names for the same Zameen location ID."""
    if a == b:
        return True
    ida, idb = _area_id(a, city), _area_id(b, city)
    return ida is not None and ida == idb


def score_case(case, filters):
    """Per-field correctness plus an area verdict: correct, flagged, silent_wrong, missing."""
    expect = case["expect"]
    fields = {}
    for field, want in expect.items():
        if field == "area":
            continue
        got = filters.get(field)
        fields[field] = (got is None) if want is None else _equal(field, got, want)

    verdict = None
    if "area" in expect or case.get("area_any"):
        want = expect.get("area")
        acceptable = set(case.get("area_any") or ([] if want is None else [want]))
        got = filters.get("area")
        flagged = bool(filters.get("area_approximate"))
        approx_ok = case.get("approx_ok", False)
        if got is None:
            verdict = "correct" if not acceptable else "missing"
        elif any(_same_area(got, ok, case["city"]) for ok in acceptable):
            if approx_ok and not flagged:
                verdict = "unflagged_approx"  # right parent, but the user isn't told the block is missing
            elif flagged and not approx_ok:
                verdict = "false_flag"  # right area, needless "no exact match" notice
            else:
                verdict = "correct"
        else:
            verdict = "flagged" if flagged else "silent_wrong"
        fields["area"] = verdict in ("correct", "false_flag") or (verdict == "flagged" and approx_ok)
    return fields, verdict


async def run_config(name, cases):
    spec = CONFIGS[name]
    if spec:
        if parsing._get_instructor_client() is None:
            raise SystemExit(f"{name}: ANTHROPIC_API_KEY is not set, so every query would silently use "
                             "the regex parser. Pass --env /path/to/.env.")
        parsing.PARSE_MODEL, parsing.PARSE_AREA_LIST = spec
        parsing._nl_cache_get = lambda key: None   # measure every call
        parsing._nl_cache_set = lambda key, value: None
    rows = []
    for case in cases:
        started = time.monotonic()
        if spec is None:
            result = parsing.parse_natural_query(case["q"], city=case["city"])
            call = {}
        else:
            result = await parsing.parse_query_with_claude(case["q"], city=case["city"])
            call = dict(parsing.last_call)
        latency = time.monotonic() - started
        answered_by = result.get("parser", "regex")
        if spec and answered_by != "ai":
            raise SystemExit(f"{name}: {case['id']} was answered by the {answered_by} parser, not Claude "
                             f"({call.get('error') or 'no error recorded'}). Stopping: the scores would be wrong.")
        filters = _build_parse_query_response(case["q"], case["city"], result)["filters"]
        fields, verdict = score_case(case, filters)
        rows.append({"id": case["id"], "city": case["city"], "lang": case.get("lang"), "q": case["q"],
                     "config": name, "ok": all(fields.values()), "fields": fields, "area": verdict,
                     "filters": filters, "expect": case["expect"], "latency_s": round(latency, 3),
                     "cost_usd": call.get("cost_usd"), "error": call.get("error"),
                     "input_tokens": call.get("input_tokens"), "cache_read_tokens": call.get("cache_read_tokens")})
    return rows


def summarize(name, rows):
    n = len(rows)
    by_field = {}
    for r in rows:
        for f, ok in r["fields"].items():
            by_field.setdefault(f, []).append(ok)
    areas = [r["area"] for r in rows if r["area"]]
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    lat = [r["latency_s"] for r in rows]
    return {
        "config": name, "cases": n,
        "exact": sum(r["ok"] for r in rows) / n,
        "fields": {f: sum(v) / len(v) for f, v in sorted(by_field.items())},
        "area": {k: areas.count(k) for k in ("correct", "false_flag", "flagged", "unflagged_approx",
                                              "silent_wrong", "missing")},
        "errors": sum(1 for r in rows if r["error"]),
        "cost_total": sum(costs), "cost_per_query": (sum(costs) / len(costs)) if costs else 0.0,
        "latency_p50": statistics.median(lat), "latency_p95": sorted(lat)[max(0, int(len(lat) * 0.95) - 1)],
        "by_lang": {lang: sum(r["ok"] for r in rows if r["lang"] == lang) / max(1, sum(1 for r in rows if r["lang"] == lang))
                    for lang in sorted({r["lang"] for r in rows if r["lang"]})},
    }


def report(summaries, rows_by_config):
    lines = ["| Config | Exact | Silent wrong area | Unflagged approx | Flagged | False flag | Missing | Errors "
             "| $/query | $5 buys | p50 | p95 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        per = s["cost_per_query"]
        buys = f"{5 / per:,.0f}" if per else "free"
        a = s["area"]
        lines.append(f"| {s['config']} | {s['exact']:.1%} | {a['silent_wrong']} | {a['unflagged_approx']} | "
                     f"{a['flagged']} | {a['false_flag']} | {a['missing']} | {s['errors']} | ${per:.5f} | {buys} | "
                     f"{s['latency_p50']:.2f}s | {s['latency_p95']:.2f}s |")
    lines.append("")
    for s in summaries:
        lines.append(f"{s['config']} fields: " + ", ".join(f"{f} {v:.0%}" for f, v in s["fields"].items()))
        lines.append(f"{s['config']} by language: " + ", ".join(f"{k} {v:.0%}" for k, v in s["by_lang"].items()))
    for name, rows in rows_by_config.items():
        silent = [r for r in rows if r["area"] == "silent_wrong"]
        if silent:
            lines.append(f"\n{name} silent wrong areas:")
            for r in silent:
                lines.append(f"  {r['id']} [{r['city']}] {r['q']!r}: got {r['filters'].get('area')!r}, "
                             f"want {r['expect'].get('area')!r}")
    return "\n".join(lines)


async def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("set")
    ap.add_argument("--configs", default="regex,haiku55-candidates")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="comma-separated case ids to run (e.g. to re-check rows after a fix)")
    ap.add_argument("--out", help="directory for per-case JSONL and the report")
    ap.add_argument("--env", help="dotenv file holding ANTHROPIC_API_KEY (read before import)")
    args = ap.parse_args(argv)
    cases = load_set(args.set)
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    cases = cases[: args.limit]
    init_db()
    names = [c.strip() for c in args.configs.split(",")]
    for name in names:
        if name not in CONFIGS:
            raise SystemExit(f"unknown config {name}; choose from {', '.join(CONFIGS)}")
    rows_by_config, summaries = {}, []
    for name in names:
        rows = await run_config(name, cases)
        rows_by_config[name] = rows
        summaries.append(summarize(name, rows))
        print(f"{name}: {summaries[-1]['exact']:.1%} exact, {summaries[-1]['area']['silent_wrong']} silent wrong areas",
              file=sys.stderr)
    text = report(summaries, rows_by_config)
    print(text)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, rows in rows_by_config.items():
            (out / f"{name}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                                               encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
        (out / "report.md").write_text(text + "\n", encoding="utf-8")
    return summaries


if __name__ == "__main__":
    asyncio.run(main())
