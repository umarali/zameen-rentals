# Natural Language Query Parsing — Learnings

## Dual Parsing Strategy

1. **Claude Haiku via Instructor** (`parse_query_with_claude`): Structured extraction using Pydantic models. Best for complex/ambiguous queries. Requires `ANTHROPIC_API_KEY`.
2. **Regex fallback** (`parse_natural_query`): Pattern matching for English, Roman Urdu, and Urdu script. Always available, no API needed.

## Roman Urdu Support

Common mappings that users expect:
| Roman Urdu | English | Filter |
|-----------|---------|--------|
| ghar, makan | house | property_type |
| flat, flaat | apartment | property_type |
| bala hissa, bala | upper portion | property_type |
| nichla hissa, nichla | lower portion | property_type |
| kamra | room | property_type |
| sasta | cheapest | sort |
| mehenga | expensive | sort |
| naya | newest | sort |
| hazar, hazaar | thousand | price multiplier |
| lac, lakh | lakh (100K) | price multiplier |

## Area Matching Challenges

The `match_area()` function uses 7 strategies in order:
1. Exact Urdu match
2. Fuzzy Urdu match (substring)
3. Roman Urdu alias (exact then substring)
4. Exact English (case-insensitive)
5. Substring match (prefer shorter/more specific)
6. Token overlap (weighted by ratio)
7. SequenceMatcher (threshold: 0.5)

**Key issue**: This aggressive fuzzy matching means "gulshan e iqbal block 13" matches "Gulshan-e-Iqbal" even though block 13 doesn't exist. The approximate match notice (added in routes.py) now warns users when their query was simplified.

## Ambiguous Queries

- "portion" alone → defaults to "upper_portion" (more common in Pakistan)
- "full house" → matches "house" (the word "full" is ignored, which is correct)
- Standalone numbers ≤ 500 in price context → treated as thousands (e.g., "50" = 50K PKR)
- "studio" → mapped to "Room" property type

## Caching NLP Results

Claude parse results are cached by query string (MD5 hash). This prevents redundant API calls for repeated queries within the 5-min TTL window.

## Model, cost controls and evaluation (2026-10-08)

The AI parser runs on Claude Haiku 5.5 (`ZR_PARSE_MODEL`, default `claude-haiku-5-5`).
On the 150-query eval set it scores 99.3% exact with no silent wrong areas, at
about $0.00012 per uncached query (roughly 41,000 queries per $5). Haiku 4.5
with the full area list scored 94.7% at $0.0066 per query.

How the cost stays low:

- **Candidate areas.** Each request lists only the ~30 areas closest to the query
  (`ZR_PARSE_AREA_LIST=candidates`), not all 300-460. `full` restores the old
  behaviour for comparison or rollback.
- **Prompt caching.** The fixed rules and examples are one cached system block;
  the city and candidates follow in an uncached block. After the first call,
  about 2,900 tokens per request are cache reads at a tenth of the input price.
- **Parse cache.** Results are kept in `nl_parse_cache` for
  `ZR_NL_CACHE_TTL_HOURS` (default 168). The key includes `PARSE_PROMPT_VERSION`;
  bump it when the prompt or post-processing changes.
- **Daily budget.** Each call's tokens and cost go into `nl_usage_daily`. Once a
  UTC day's spend reaches `ZR_NL_DAILY_BUDGET_USD` (default 1.00), queries use
  the regex parser until midnight UTC.

Post-processing after the model:

- An area that matches no real area is dropped, then the landmark lookup runs.
- `_reconcile_ai_area` makes the area agree with areas the query names.
- `_drop_area_number_beds`: "askari 5 flat" isn't 5 bedrooms.
- `_prefer_regex_numbers`: bedrooms, prices and sizes come from the regex
  parser when it finds them, since it handles units and number words
  deterministically.

Evaluate a change before shipping it (AI configs cost money; check the
estimate in the script's docstring):

```bash
python3 tools/eval_nl_parser.py tests/fixtures/nl_eval_queries.jsonl \
  --configs regex,haiku55-candidates --env .env --out /tmp/nl-eval
```

The harness refuses to run an AI config without an API key, and stops if any
query is answered by the regex fallback, so a missing key or exhausted credit
can't produce plausible-looking scores. The number to watch is "silent wrong
area": a wrong area shown without the "No exact match" notice.
