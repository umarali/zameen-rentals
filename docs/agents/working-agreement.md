# ZameenRentals engineering working agreement

This document configures the locally adapted skills selected on 10 October 2026. The source manifest is `skills-lock.json`; exact copies live under `tools/agent-harness/skills/`. The selection combines Matt Pocock's focused engineering skills and Lauren Tan's official PStack skills. These are local Codex adaptations, not official Codex distributions from either author.

## How to work

1. Deliver anything Umar is asked to review as HTML. Keep editable sources and evidence alongside it. State the decision first and link directly to the evidence behind findings.
2. Use the current task and repository as the scope. Read the current diff, call path and existing tests. Do not turn review-only work into fixes or make deployment part of a local change.
3. Clarify only material unresolved choices. The current session's instructions and settled decisions persist. Research facts instead of asking Umar to look them up.
4. Diagnose before fixing. Build a small repeatable check that fails on the actual symptom. For persistence bugs, exercise real SQLite transactions in a disposable database.
5. Implement one complete behavior at a time. Reuse the project's existing interfaces. Avoid speculative wrappers, extra features and unrelated cleanup.
6. Keep evidence and interpretation separate. Show denominators and uncertainty. For this trust project, high-confidence findings need concrete support; experimental product choices stay separately identified. Confidence labels are not substitutes for evidence.
7. Preserve time and provenance. Distinguish source dates, fetched-at, first-seen, cached values and imported observations. Do not infer creation, freshness or availability from the wrong clock.
8. Verify proportionately. Use focused Python/API tests for behavior, headless browser checks for UI changes, and the Vite build for frontend changes. Avoid tests of trivial wording or tests that mirror the implementation. Broaden checks when risk or failures justify it.
9. Protect the working environment. Analyze live local data via read-only access and disposable copies. Use owned test servers and free ports. Do not stop another process or install browsers without an explicit reason and authorization. Honor any active no-paid-API or no-production-access constraint.
10. Measure before making performance claims. Check correctness, executed work, sample size, noise and end-to-end relevance. A copied database on a Mac is useful evidence, not a 1-vCPU Droplet benchmark.
11. Obtain the required Claude review of the exact candidate and resolve material findings before applying shared edits or presenting completion. The reviewer runs outside active worktrees. See `claude-verification.md`.
12. Close out with the outcome, tests and remaining limitations. Keep the review HTML in sync with its source. Leave commits, external publication and deployment governed by the active user's request.

## Skill routing

- Unclear product decision: `grilling`, or `grill-with-docs` when terminology/decisions should be recorded. Use `grilling` directly; a global `grill-me` alias is optional and outside this branch.
- Settled feature to describe or divide: `to-spec` then `to-tickets` as needed. Read `issue-tracker.md` first; local files are the default.
- Hard bug: `diagnosing-bugs`. Use `tdd` for the failing-test/fix loop at the agreed behavior boundary.
- Module or domain change: `codebase-design` and `domain-modeling` only as needed.
- Explain a call path: `pstack-how`.
- Check hidden callers, storage and cache consequences: `pstack-blast-radius`.
- Make or judge a performance claim: `pstack-benchmark-checklist`.
- Produce a review artifact: `html-review`. Use the existing `unslop` writing filter when available.

## What is deliberately not enabled

The required Claude Opus 5.5/high reviewer is the only model-review procedure enabled by this harness. No automatic PStack mode, model panels, swarm, overnight shipping, auto-merge, auto-update or external tracker integration is enabled. See `claude-verification.md` for the review gate and its authorization limits.

Matt's upstream skill content is retained where useful, with documented changes for Codex tools, HTML output, local planning, proportional documents and existing authorization. PStack tracing and impact checks run honestly as one-agent work unless delegation is authorized. Upstream licenses and revision metadata are included per skill.

## Updating

Read the versioned skill's `SOURCE.json`, compare the pinned revision with the proposed upstream revision, and inspect tool assumptions and side effects before updating. Do not run bulk automatic updates over these local adaptations. Preserve local changes and update the manifest with any accepted revision.
