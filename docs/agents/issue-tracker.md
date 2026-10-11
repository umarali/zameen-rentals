# Issue tracker for the installed engineering skills

Default to local files. This is an agent planning convention, not a claim that the repository has no external issue tracker.

- Specs: `docs/plans/<feature>/spec.md` with `spec.html` for review.
- Tickets: `docs/plans/<feature>/issues/<NN>-<slug>.md` in dependency order, with a reviewable `index.html` for the plan.
- Each ticket records observable acceptance criteria, blockers and a status. Use `ready-for-agent` only when the behavior is sufficiently specified; otherwise use `needs-info` and state the open decision.
- Generate the HTML from the current source before presenting it. The HTML is the primary human review artifact; Markdown is the editable supporting source.
- Use the tracker explicitly named in the active task when one is supplied. Do not create external issues, labels or PRs merely because an upstream skill mentions publishing.
- Reuse agreed scope and test interfaces. Ask only about material unanswered questions; no repeated approval for routine task decomposition.
