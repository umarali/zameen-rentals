Requested model: claude-opus-5-5. Effort: high. Executed through Claude Code using the existing subscription. Provider metadata confirmed claude-opus-5-5. This is a source review, not test execution. Jev source was excluded; its Jev section is conceptual and its suggestion to treat a typed provider as the authority is challenged in the main report.

# ZameenRentals: Claude/Instructor integration review

**Scope.** I read the provided source only. I didn't run anything. The Jev source is on a separate branch and wasn't provided, so the Jev section is conceptual. I also didn't have `tests/test_claude_integration.py` (untracked), the frontend `main.js`/`filters.js`, or `app/data.py`. Wherever a finding depends on those files, I say so.

## Findings, ranked

**D1 (High). An off-list AI area survives normalization.** In `app/parsing.py` · `parse_query_with_claude`:
```python
result["area"] = matched if matched else result.pop("area", None)
```
- When `matched` is None, `pop` returns the bad name and the assignment puts it straight back. The `is None` check never fires.
- **Repro:** use a fake client that returns `RentalFilters(area="Zzqx Heights")` for a query with no literal area span. The result is `{"area": "Zzqx Heights", "parser": "ai"}`, cached for 5 minutes.
- In `_build_parse_query_response`, the area isn't in `areas`, so the approximate flag and the "did you mean" suggestions are both skipped.
- In `/api/search`, a name-only filter returns 0 local results, so it falls through to a live scrape. `build_url` → `match_area` returns None, which produces a **city-wide URL**.
- So if the frontend forwards `filters.area` (not verified), the renter gets city-wide results labelled with a fake area.
- **Realistic trigger:** on the Karachi tab, "F-8 mein 2 bed flat". The few-shot example teaches `"F 8"` with no `city_hint`, so the model can return a name that isn't in the Karachi list.
- **Fix:** `if matched: result["area"] = matched` `else: result.pop("area")`.

**D2 (High). The timeout doesn't cancel the call.** `asyncio.wait_for` over `asyncio.to_thread(sync_client.messages.create)` abandons the thread but doesn't stop it.
- No `timeout` or `max_retries` is passed, so the Anthropic SDK and Instructor defaults apply. The SDK default timeout is long, and SDK retries are multiplied by Instructor's validation retries. Late results are billed and then thrown away, because `cache_set` never runs.
- All of this happens in the **default executor**, which `voice.transcribe` also uses. On a 1-vCPU box that pool is small. A few hung Claude calls can stall voice transcription, and voice then holds its semaphore while it waits.
- **Repro:** make the fake `messages.create` call `time.sleep(60)`. Fire about 5 parse requests, then one voice request. The voice request blocks.
- **Fix:** switch to the async client and set every budget explicitly:
```python
instructor.from_anthropic(anthropic.AsyncAnthropic(api_key=key, timeout=httpx.Timeout(4.0, connect=1.5), max_retries=0))
await client.messages.create(..., response_model=RentalFilters, max_retries=0, temperature=0)
```
  Keep the SDK timeout below the route's 8 s so the regex fallback runs cleanly, and add a circuit breaker.

**D3 (Med). No outage or cost guardrails.**
- There's no circuit breaker. During an API slowdown, every parse waits up to 8 s before falling back.
- `q` has `min_length=1` but no `max_length`, so arbitrarily long queries (up to URL limits) go to the model.
- Rate limiting is per IP only. There's no global AI-call budget.
- The cache key is the raw query, so case and whitespace variants each miss the cache.

**D4 (Med). The AI schema and prompt disagree with backend semantics.**
- **Karachi size units:** the regex parser handles gaz and sq yd (divides by 25), but the prompt only covers marla and kanal. For "120 gaz ghar", the model may set `size_marla_min=120`, which returns zero results. This is untested; it needs an eval case.
- **Bedrooms:** the description says "Minimum (or exact)", but `_listing_filter_clauses` uses `bedrooms = ?`, which is exact. A query like "3+ bed" gets an exact-3 filter (the regex parser has the same problem). For N+, set `bedrooms_max=10`.
- **Unfurnished:** `furnished=false` is silently ignored, because the filter checks `if furnished:`. A renter asking for unfurnished still sees furnished listings.

**D5 (Med). An inverted price range breaks search (both parsers).**
- **Deterministic repro:** `parse_natural_query("flat 80k se 50k")` returns `price_min=80000, price_max=50000`.
- `/api/search` then fails `_validate_price_range` with a 400.
- The AI path checks the ordering of bedrooms and size, but not price.
- **Fix:** swap the values once in `_build_parse_query_response`, which covers both parsers.

**D6 (Med). Urdu script in Lahore and Islamabad.**
- Urdu matching in `_area_spans` and `match_area` is gated on `city == "karachi"`. Unless `ROMAN_URDU_AREAS_BY_CITY` holds Urdu-script keys for those cities (not visible to me), the regex parser finds no area for "گلبرگ میں فلیٹ".
- The AI path can find it, but `_build_parse_query_response` then always flags it `area_approximate`: Urdu tokens never intersect English area tokens.
- `area_query` is built with `" ".join(set)`, so its word order changes across processes because of string hash randomization.
- `voice.py` seeds Lahore and Islamabad Urdu area names into Whisper's prompt, so voice search hits this path by design. The Playwright server forces regex, so no end-to-end test covers it.

**D7 (Low/Med). Prompt hygiene.**
- The few-shot examples contradict the `city_hint` rule: "Defence Karachi" has no hint, and the cross-city examples (F-8, Johar Town) have none either.
- `temperature` is unset (default 1.0), so the same query can parse differently between cache windows.
- The model ID is hard-coded; an environment variable would allow rollback and A/B tests.
- The system block has no `cache_control`. Measure the per-city prefix with token counting and add caching if it exceeds the model's documented minimum cacheable length.

**D8 (Low). Curated landmarks lose to the model's guess.** `resolve_landmark` only runs when the model returns no area. When it hits and there's no literal area span, prefer the landmark, or flag the disagreement.

**D9 (Low). Observability.**
- Nothing records token usage, latency, or regex-vs-AI disagreement. `create_with_completion` would expose usage.
- `log_search` doesn't store which parser produced the filters.
- `except Exception` also swallows post-processing bugs, so log `exc_info`.
- Suggestions use `city` while the rest of the route uses `effective_city`. Whether the frontend switches city on `city_hint` needs checking.

## Top 5 opportunities

**1. Fast-or-absent AI parsing.**
- **Renter benefit:** an instant search box on slow mobile networks.
- **Integration point:** in `api_parse_query`, run the regex parser first. Call Claude only when the regex result has no area, is `area_approximate`, or leaves unparsed words after `_strip_noise_tokens`. Otherwise race Claude against a short budget (around 2–3 s).
- **Gate:**
  - With a 60 s fake client, the route returns regex output in under the budget and no thread is left running.
  - A concurrent voice request still completes.
  - Measure p95 latency and fallback rate before and after.

**2. Grounded area choice.**
- **Integration point:** build candidates deterministically from `_area_spans`, `match_area`, `suggest_areas` and `resolve_landmark`. Have the model return:
  - `area_text`, which must be a verbatim substring of the normalized query or it's dropped;
  - `area_choice`, constrained to that candidate list plus `"none"`.
- **Renter benefit:** "did you mean" chips instead of a silently wrong area. It also shrinks the prompt.
- **Gate:**
  - A property test over random model outputs: the area is always in `get_areas(effective_city)` or absent.
  - Area accuracy is at least as good as the current path on the golden set.

**3. Offline alias generation for Lahore and Islamabad.**
- **Integration point:** a `tools/` script uses Claude, via the Message Batches API, to propose Urdu-script and Roman Urdu aliases. People review them before they go into the per-city maps in `data.py`. Remove the `karachi` gates in `_area_spans` and `match_area`.
- **Renter benefit:** fixes regex and voice search for two of the three cities. Runtime stays deterministic and free.
- **Gate:**
  - Only reviewed aliases ship.
  - Each alias maps to exactly one area per city.
  - No alias collides with `_AREA_NOISE` or `_NUMBER_WORDS` (for example "do" or "sath").
  - Golden Urdu-script queries pass for each city.

**4. Fact extraction from stored listing descriptions (crawler, offline).**
- **Facts:** furnishing, family/bachelor restrictions, advance or deposit months, whether maintenance is included, separate meters or entrance.
- **Grounding rules:** every fact carries a quote that must be a substring of `description`. A fact with no valid quote is discarded, and absence means unknown, never inferred.
- **Integration point:** a `listing_facts` table keyed by `detail_hash`, so extraction reruns only when the detail changes.
- **Why it matters now:** the current `LIKE '%furnished%'` filter also matches "semi-furnished". If `details_json` stores a furnishing key, it matches whatever the value is.
- **Gate:**
  - Measure precision on a hand-labelled sample per city and language before any filter uses a fact.
  - Measure coverage first, and skip filters for facts that rarely appear.

**5. Evaluation harness and shadow telemetry.**
- **Golden set:** cases across city × script (English, Roman Urdu, Urdu) × feature, including gaz units, "N+", inverted ranges, "X or Y", landmarks, and cross-city names.
- **Shadow logging:** record regex-vs-AI disagreement, with digit runs of 7+ redacted to keep phone numbers out.
- **Gate to enable AI for a field:**
  - AI matches or beats regex for that field in each city and script.
  - Zero off-list areas.
  - Measured p95 latency, and cost per 1,000 queries taken from `usage`.

## Jev (typed decision provider) and Claude, conceptually

- **Division of labour:**
  - Claude handles perception: turning Urdu, Roman Urdu or English text into a *proposal* in a typed schema, and later explaining decisions in the user's language.
  - The typed provider is the authority. It validates proposals against allowed values, resolves conflicts between regex and AI with reason codes, and decides.
  - Claude never writes final filters or rankings directly.
- **Natural seams in this code:**
  - `_reconcile_ai_area` plus the post-validations in `parse_query_with_claude` are already an ad-hoc typed arbiter. Consolidating them into one `decide(regex, ai, spans, city)` function is where Jev would fit.
  - `compare.js` `buildVerdict` ranks by Rs/marla even across property types (room vs house). A typed provider could refuse cross-type verdicts and emit reason codes, and Claude could explain those codes without adding facts.
- **Gates (to confirm against Jev's real interface):**
  - Decisions can be replayed exactly from logged inputs.
  - Claude's explanation only references fields and reason codes the provider returned.
  - Disagreements show up as visible chips, never silent overrides.