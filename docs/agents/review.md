# Agent harness review

**This branch packages the review workflow for inspection.** It contains the standing rules, twelve pinned skill copies, the HTML renderer and a command-line runner for independent Claude review. Checking out the branch does not install skills, modify your global settings or change the rental application.

## Branch and scope

The branch is `chore/agent-harness-review`, created in a separate clone after `git pull --ff-only origin main`. The starting main commit is `e9506fc6eb513173c412f4cd2631111aff3cd3ab`. The final push procedure pulls main again and verifies the branch contains the fetched commit.

Only `AGENTS.md`, `docs/agents/` and `tools/agent-harness/` are in scope. The existing main checkout and Claude's active worktrees stay untouched. The prior listing-trust implementation review and experimental date changes are not included.

## The working rules

| Rule | Concrete behavior |
| --- | --- |
| HTML first | Reviews, plans and other substantive material for Umar have an HTML primary deliverable. Editable Markdown and raw evidence remain supporting sources. |
| Independent review | Request exactly Claude Opus 5.5 with high effort before declaring completion or applying shared edits. No silent model fallback. |
| Evidence attached | Send the exact candidate and meaningful test evidence. Record the returned model, requested effort, verdict and file hashes. |
| Recheck changed files | A changed candidate needs another review. Verify hashes again before applying or publishing. |
| Protect concurrent work | Inspect branches and ownership, prepare overlapping work in isolation, and never overwrite or stop Claude's work. |
| Test real behavior | Reproduce the symptom, test the relevant contract, and use real disposable storage for transaction behavior. |
| Keep claims bounded | Distinguish observations from inference and state what remains unverified. High effort is a requested CLI setting, not independently attested metadata. |
| Keep authorization scoped | The user's request authorizes these review calls through the existing subscription. It does not enable billing, external publication or deployment beyond the active task. |

Read the full [working agreement](working-agreement.md) and [Claude verification rule](claude-verification.md). The root instruction change points to these documents instead of copying them into every skill.

## Selected skills

| Source | Skill | Purpose |
| --- | --- | --- |
| Matt Pocock | `diagnosing-bugs` | Build a symptom-specific reproduction before choosing a fix |
| Matt Pocock | `tdd` | Verify one behavior at a time through a meaningful interface |
| Matt Pocock | `codebase-design` | Design useful modules and caller contracts |
| Matt Pocock | `domain-modeling` | Keep terminology and durable decisions precise |
| Matt Pocock | `grilling` | Resolve material unanswered design decisions |
| Matt Pocock | `grill-with-docs` | Combine design questions with useful domain records |
| Matt Pocock | `to-spec` | Turn settled discussion into a proportional specification |
| Matt Pocock | `to-tickets` | Divide scope into complete, verifiable work with dependencies |
| Lauren Tan / PStack | `pstack-how` | Trace the actual runtime call path |
| Lauren Tan / PStack | `pstack-blast-radius` | Prove assumptions about callers, storage and caches |
| Lauren Tan / PStack | `pstack-benchmark-checklist` | Check correctness, work performed, fairness and measurement limits |
| Local | `html-review` | Produce a standalone review document and retain its evidence |

These are local Codex adaptations, not official distributions from either author. They replace tool assumptions that do not fit Codex, preserve existing authorization, and avoid mandatory external model panels. PStack's useful evidence procedures remain. Upstream licenses, revisions and changes are recorded per skill and in the [inventory](skills-lock.json).

Sources are [Matt Pocock's repository](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336) and [Lauren Tan's official PStack](https://github.com/cursor/plugins/tree/d73344bee8cf22e53b9d5f4cf5749d38ba38c174/pstack).

## How the review runner works

The runner takes a sanitized context file and an explicit list of text files. It snapshots their contents and modes, launches a new tool-disabled Claude session outside the checkout, and asks for a structured verdict. It writes a PASS receipt only when the exact model is confirmed, no material findings remain, and the files still match their snapshots.

A separate `check` command verifies the receipt and selected files before applying changes. The runner never modifies the candidate, stages files, commits or pushes. It does not discover omitted files or prevent a human bypass. It is a local review aid, not a signed security control.

The [usage guide](../../tools/agent-harness/README.md) has the commands and limits. Raw review packets remain outside the repository because they can contain local paths or sensitive context. Publish only a sanitized review receipt when appropriate.

## What to inspect

- [Root project instructions](../../AGENTS.md): the small routing change.
- [Verification policy](claude-verification.md): exact-model gate and concurrency rules.
- [Review runner](../../tools/agent-harness/review.py): invocation, verdict handling and content checks.
- [Offline tests](../../tools/agent-harness/tests/test_review.py): rejection and integrity cases.
- [Skill inventory](skills-lock.json): sources and hashes for the exact copies.
- [HTML renderer](../../tools/agent-harness/skills/html-review/scripts/render_review.py): offline output and source-content handling.

## Validation and limitations

Validation for this branch consists of the offline runner tests, the twelve-skill inventory check, headless HTML checks, and independent Opus review of the substantive candidate. The final sanitized review receipt is recorded separately so the receipt itself does not trigger recursive review.

This change does not run or alter the application, crawler or production database. Application suites are not substitutes for the harness-specific checks and are not needed for unchanged application code. The skills themselves are instructions; static validation is not proof of their behavior in every future task.

The review runner requires Python 3.10 or newer and a compatible Claude CLI with an existing subscription login. It sends the selected content to Claude and shares the account's usage limits. An operator must inspect the input for secrets and confirm that the file list covers the intended change.

Do not install a duplicate global skill bundle when those names already exist. You can read the versioned copies directly. Nothing here enables auto-merge, deployment or unattended shipping.
