---
name: pstack-how
description: Trace how a subsystem works, including its entry point, runtime flow, data transformations and ownership. Use for code walkthroughs and placement questions.
---

## Local Codex integration

This is a local adaptation, not an official Codex release. See `SOURCE.json` for the pinned upstream and modifications.
Use available Codex tools; a request to read another skill means read its local `SKILL.md`, not call a nonexistent Skill tool. User instructions and the current authorized task take precedence. Skills do not authorize commits, publication, paid model calls, deployments or broader work. Use the inherited model; delegate only when the user or applicable active instructions authorize it. For material the user is asked to review, use `html-review` and provide the HTML link.

# Trace how it works

Read the actual implementations, not just symbol names. Start at the user action, API handler or scheduled job and follow the data through its callers, storage, cache and response. Name missing links honestly.

For a narrow question, inspect and explain directly. For a broad question, divide it into two to four distinct investigation angles and inspect each. Use parallel read-only agents only when the user or active task instructions authorize delegation, with available tools and the inherited model unless otherwise requested. Do not claim independent or cross-model review when it did not happen.

Use [the exploration guide](references/explorer-prompt.md) for what to trace and [the explanation guide](references/explainer-prompt.md) for the resulting explanation. These are guides you can apply directly, not mandatory subagent prompts. Reconcile contradictory evidence by reading code or running a safe diagnostic. Cite files and lines; distinguish observed runtime behavior from an inference from code.

Present the answer at the level the reader needs. Include a diagram only when it reduces explanation effort. For a reviewable walkthrough, produce HTML with the conclusion, key flow, relevant files and unresolved questions. Do not modify application code unless that is also requested.
