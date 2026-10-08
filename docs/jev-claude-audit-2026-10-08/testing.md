Test English and Urdu search locally with disposable sample listings. This avoids your real database and makes the expected results predictable.

From `zameenrental`, run:

```bash
npm run build
PLAYWRIGHT_PORT=8127 python tests/serve_playwright.py
```

Open http://127.0.0.1:8127/ yourself. This server uses the regex fallback and seeded listings, so it needs no Claude credits. Stop it with Ctrl+C afterward.

Select the indicated city, press Clear All before each query, and check the filter chips and results. Each row's two queries should give the same area, apartment type, two bedrooms, and a PKR 50,000 maximum rent. The sample data includes matching apartments in all three areas.

| City | English | Urdu | Expected area |
|---|---|---|---|
| Karachi | `2 bed flat in Clifton under 50k` | `کلفٹن میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک` | Clifton |
| Lahore | `2 bed flat in Gulberg under 50k` | `گلبرگ میں دو کمروں کا فلیٹ پچاس ہزار تک` | Gulberg |
| Islamabad | `2 bed flat in F-10 under 50k` | `ایف ۱۰ میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک` | F 10 |

Check these additional details:

- Search `5 marla house in Johar Town under 1 lakh` and `جوہر ٹاؤن میں پانچ مرلہ گھر ایک لاکھ تک` in Lahore. The expected filters are Johar Town, house, minimum 5 marla and maximum PKR 100,000. The sample dataset has no Johar Town listings, so zero results are expected.
- Search `کلفٹن میں ۱۲۰ گز گھر` in Karachi. Expect house, Clifton, and 4.8 marla minimum, which is 120 square yards.
- Remove the bedroom chip after a search. Its filter should clear and results should refresh.
- Repeat on a narrow/mobile viewport. The same filters should apply.

To run the automated checks, first stop the manual server, then run:

```bash
ANTHROPIC_API_KEY='' python -m pytest tests/test_search_languages.py tests/test_claude_integration.py -q
PLAYWRIGHT_PORT=8127 npx playwright test tests/search-languages.spec.js tests/nl-search.spec.js
```

Playwright is configured headlessly. The Python checks cover both English/Urdu fallback parsing and the Claude SDK boundary with mocked HTTP, including deadline cancellation and failures. Live Claude parsing is a separate check: once the API account has credits, run the normal app with its configured key and repeat these queries. `/api/parse-query` returns `parser: "ai"` when Claude actually answered. A regex result is not evidence that the live AI worked.

The integrated tree includes the Jev fixes. From the repository root, run its targeted deterministic tests:

```bash
ANTHROPIC_API_KEY='' python -m pytest tests/test_decisions.py tests/test_listing_tags.py tests/test_eval_listing_tags.py tests/test_strict_audit.py tests/test_jev_hardening.py -q
```

These tests use disposable databases and fake providers. They verify that edited listings lose their old tags, stale in-flight answers cannot restore them, cached browse results refresh tags, invalid API replies are rejected, and unlabelled evaluation fields are excluded. No live listings are tagged.

For a live Jev smoke check, run from the same repository root:

```bash
python tools/eval_jev_smoke.py --source . --out /tmp/jev-smoke-results.json
```

This uses the existing TypeSafe key and sends 15 synthetic English/Urdu descriptions through the current questions and publication guard. It does not read or update production listing data. It exits nonzero if a case fails or the run is incomplete. All 15 passed during this fix, but this small synthetic set is not a representative accuracy benchmark.

Jev currently exposes tags through `/api/search` parameters such as `tenant=bachelor`, `backup_power=true` and `separate_entrance=true`. It has no tag controls in the frontend yet. A regular browser search therefore cannot verify those filters visually. The API tests above exercise them directly.

On eventual deployment, legacy tags intentionally become unavailable until rescored under the new pipeline version. Normal browsing still works. The branch integration does not run a production migration, retagging or deployment.
