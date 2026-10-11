# Domain documentation

Use one project context. Read `GLOSSARY.md` if present and relevant decisions in `docs/adr/` before changing domain meaning. Create these files lazily when a term is settled or a material architectural tradeoff needs recording; do not generate placeholders.

For listing-trust work, consult the evidence and reviews under `docs/listing-trust-2026-10-10/` in the relevant worktree. Preserve these distinctions:

- Source Added/Updated labels and lifecycle epochs are source claims with observation times.
- Our first-seen timestamp is discovery by a particular database/crawler, not original listing creation or confirmed availability.
- A cache read is not a new upstream fetch. Local imported history is not production observation history.
- A reported same-ID date change does not establish the actor or mechanism that caused it.

Separate raw observation, normalization and interpretation in code and documentation. A date belongs with its source and observation time. Add HTML counterparts whenever domain or decision documents are presented to Umar for review.
