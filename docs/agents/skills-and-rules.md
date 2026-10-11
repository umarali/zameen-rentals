# Your engineering rules and skills

**HTML is now the default for anything I ask you to review.** The rule is saved globally in your Codex instructions and repeated in this project's guidance. It applies to plans, audits, proposals, comparisons, specifications and reviews. An explicit request for another format still takes precedence.

The setup is complete: **8 Matt Pocock skills + 3 Lauren Tan PStack adaptations + 1 local HTML-review skill.** Your existing `grill-me` alias now resolves to the installed `grilling` skill. Existing skills, including `unslop`, were preserved.

## The rules that matter

| Rule | What it changes in practice |
| --- | --- |
| Review in HTML | The final reply links a readable, standalone HTML document. Markdown and raw evidence stay as supporting sources. |
| Prove the claim | Separate observed facts, inferences and unknowns. Findings name the failure, evidence and limits. Confidence percentages never replace evidence. |
| Diagnose before fixing | Reproduce the user's symptom with a small, repeatable check before changing behavior. |
| Test the contract | Exercise behavior at the right interface. Use real disposable SQLite databases for persistence and rollback contracts. |
| Keep the change focused | Finish the requested behavior without speculative abstractions, unrelated cleanup or added product scope. |
| Preserve meaning | Keep source dates, observation times, cached values and first-seen timestamps distinct. |
| Measure honestly | Include units, sample size, environment and variation. A local diagnostic is not a production performance guarantee. |
| Ask only what matters | Reuse settled decisions and existing authorization. Research facts directly; ask about material unanswered product choices. |
| Verify in proportion | Use targeted checks first, broaden them when risk or failures justify it, and keep browser tests headless. |
| Keep authority with the task | Installing a skill does not authorize external publication, paid calls, production access or deployment. |

These are working defaults chosen for this project, not a claim that one workflow is best for every team. The [working agreement](working-agreement.html) gives the complete rules and routing.

## Matt Pocock's selected skills

The source is [Matt Pocock's official skills repository](https://github.com/mattpocock/skills). I selected the reusable engineering disciplines and planning tools, then adapted their environment assumptions. Each installed folder includes its MIT license and `SOURCE.json` with the exact revision and local changes.

| Installed skill | Use it for | Why it belongs here |
| --- | --- | --- |
| `diagnosing-bugs` | A hard failure or regression | Builds a symptom-specific feedback loop before choosing a fix. This directly fits the SQLite rollback finding. |
| `tdd` | A test-first bug fix or feature | One failing behavioral test, one implementation step, then verification. The local adaptation explicitly permits real persistence checks. |
| `codebase-design` | Interface and module design | Helps decide which component owns a contract and keeps complexity out of callers. Useful around scraper, cache and database responsibilities. |
| `domain-modeling` | Precise terminology and durable decisions | Keeps source date, observed-at, first-seen and availability from becoming interchangeable terms. |
| `grilling` | Stress-testing an unsettled decision | Batches the questions that matter and looks up facts first. It is not an interview imposed on every small edit. |
| `grill-with-docs` | A design discussion that should leave useful documentation | Combines decision questions with glossary and architectural decision records when needed. |
| `to-spec` | Turning settled discussion into a specification | Records the requested outcome, acceptance criteria, decisions and non-goals. Local files are the configured default. |
| `to-tickets` | Splitting a plan into verifiable work | Produces complete, dependency-aware slices rather than disconnected backend/frontend task lists. |

`grill-with-docs`, `to-spec` and `to-tickets` retain their upstream explicit invocation metadata. The other skills remain available for relevant tasks. The existing `grill-me` stays an explicit interview shortcut.

## Lauren Tan's selected PStack skills

Lauren is **Lauren Tan, “poteto.”** The official source is [PStack in Cursor's plugin repository](https://github.com/cursor/plugins/tree/main/pstack); its plugin metadata names her as the author. These three are namespaced local Codex adaptations.

| Installed skill | Use it for | Why it belongs here |
| --- | --- | --- |
| `pstack-how` | Tracing how a subsystem works | Follows entry points, call chains, state and outputs before explaining the behavior. |
| `pstack-blast-radius` | Checking what a small change might break elsewhere | Examines callers, storage, wire formats and caches, then tries to prove the key safety assumption with real code. |
| `pstack-benchmark-checklist` | Judging a speedup, regression or capacity measurement | Checks that work actually happened, outputs were correct, comparisons were fair and noise is understood. |

The existing `unslop` skill remains your writing filter. I did not install a second copy.

## What I adapted

- Replaced Cursor-specific execution assumptions and unsupported Skill-tool calls with available Codex tools and local skill reads.
- Removed mandatory named external model calls. PStack tracing and impact work can run with the current agent; delegation is used only when authorized. A single-agent result is never presented as independent consensus.
- Added HTML as the human review deliverable while retaining useful Markdown and evidence sources.
- Configured planning to use local files. Upstream instructions to publish issues do not silently create GitHub activity.
- Removed redundant test-interface approval prompts when scope and behavior are already established. Genuine unresolved decisions still get a question.
- Made specifications proportional to the task rather than requiring an exhaustive user-story list.
- Preserved real SQLite verification as valid for persistence contracts. Tests should observe the actual guarantee, not merely a mocked call.
- Added the macOS core-count command to PStack's benchmark checklist and preserved ownership of other running processes.

These changes are disclosed local adaptations. They are not official releases or endorsements from either author.

## What I deliberately left out

**No full automatic PStack mode, swarm or shipping workflow.** Those bring broader routing, model configuration and operational behavior than this project currently needs. The selected disciplines address the problems demonstrated in the review without adding an always-on orchestration layer.

**No duplicate TDD or writing stack.** Matt's TDD is the testing reference; your existing `unslop` is the writing filter. Existing engineering review skills remain available.

**No automatic updates.** These copies are pinned so a future upstream change cannot silently change how the agent behaves. Update by inspecting the upstream diff and preserving local adaptations.

## How we will use this next

For the listing-trust work, the useful sequence is:

1. `diagnosing-bugs` to reproduce the SQLite rollback failure in a disposable database.
2. `tdd` to capture the transaction contract and verify the fix when implementation is authorized.
3. `pstack-blast-radius` to inspect batch writes, alert hooks, cached details and affected callers.
4. `pstack-benchmark-checklist` if the fix changes write cost or sort performance.
5. `html-review` to present the result, evidence and remaining limitations.

For a new product direction, start with `grill-with-docs` only when there are material design decisions to resolve, then use `to-spec` and `to-tickets` as needed. A routine correction can go straight to diagnosis and implementation within the requested scope.

No listing-trust bugs were fixed as part of this setup. The [implementation review in HTML](/Users/umarali/Workspace/MVPs/zameenrental-trust-dates/docs/listing-trust-2026-10-10/implementation-review.html) still records the merge-after-fixes verdicts.

## Where the setup lives

| Location | Purpose |
| --- | --- |
| `/Users/umarali/.codex/AGENTS.md` | Global HTML-review rule and engineering defaults |
| `AGENTS.md` in this repository | Project routing to the working agreement |
| `/Users/umarali/.codex/skills/` | Twelve installed skill folders |
| `/Users/umarali/.agents/skills/grill-me/SKILL.md` | Repaired existing interview alias |
| `docs/agents/working-agreement.md` | Project workflow source, with HTML counterpart |
| `docs/agents/issue-tracker.md` | Local spec/ticket convention |
| `docs/agents/domain.md` | Domain-document and listing-trust terminology guidance |
| `docs/agents/skills-lock.json` | Upstream revisions, adaptation notes and installed file hashes |
| `/Users/umarali/.codex/backups/2026-10-10-html-skills/` | Previous instruction files and installation receipt |

The HTML documents are standalone and make no network requests for fonts or scripts. Local evidence links need the original workspace; a shareable export would need portable evidence attachments or repository URLs.

## Verification and source versions

All **12/12** installed skills passed the Codex skill validator. The renderer was exercised on the complete prior implementation review and this guide. All 6/6 headless document/viewport checks passed at widths 1440 and 375: no page-wide overflow, broken navigation anchors, browser errors or external requests. The full prior review text and all eight findings were preserved. [Validation details](html-validation.json) are saved alongside this guide. Application tests were not rerun because no application code changed.

| Source | Pinned revision |
| --- | --- |
| [Matt Pocock](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336) | `49dd158d1076134a641b33efb035946536778336` |
| [Lauren Tan's official PStack](https://github.com/cursor/plugins/tree/d73344bee8cf22e53b9d5f4cf5749d38ba38c174/pstack) | `d73344bee8cf22e53b9d5f4cf5749d38ba38c174` |

The source manifest and each skill's `SOURCE.json` preserve more detail than this guide. New skills are available on the next turn after installation. No commits, deployments or external tracker writes were made.
