# Agent review harness

This packages the HTML-first workflow, pinned Matt Pocock and Lauren Tan PStack adaptations, and the Opus review procedure used for ZameenRentals. It does not change the application runtime or install anything automatically.

Start with [the HTML overview](../../docs/agents/review.html), [working agreement](../../docs/agents/working-agreement.md), and [verification rule](../../docs/agents/claude-verification.md).

## Contents

- `skills/`: twelve versioned skill copies, including licenses and source metadata. Read the relevant `SKILL.md` directly or install a selected copy through your normal skill workflow after checking for an existing installation. Do not install a second copy alongside an existing global skill with the same name.
- `review.py`: explicit file-snapshot review through the existing Claude subscription, with exact-model validation and content hashes.
- `tests/`: offline checks of rejection, integrity and authentication-failure behavior.
- `requirements.txt`: dependencies for the bundled HTML renderer only. The review runner uses Python's standard library.

## Review a candidate

Use Python 3.10 or newer and a Claude Code CLI that supports the flags below. This procedure was exercised with Claude Code 2.1.284. Check `claude --help` on another version; do not silently remove isolation or model flags to make an older version run.

Prepare a sanitized context file outside the checkout. Include the task, intended file scope, base commit, relevant before/after behavior and test evidence. Review every file you intend to publish, including supporting references. Check the proposed file list for credentials and personal data before sending it. This helper transmits the selected files and context to Claude; it does not automatically redact them.

```bash
python3 tools/agent-harness/review.py review \
  --root "$PWD" \
  --context /tmp/harness-context.txt \
  --output /tmp/harness-review-unique \
  --files AGENTS.md docs/agents/claude-verification.md
```

The output directory must be new and outside the candidate checkout. The example intentionally selects only two files; it does not review the entire branch. Include the complete intended scope for a real branch review. The runner rejects symlink files, escaping paths and oversized packets. It takes one model call and has no retry or fallback loop.

The runner checks the existing `claude.ai` login, requests `claude-opus-5-5` with `--effort high`, disables tools/customizations/MCP/session persistence, and runs outside the candidate checkout. It will not enable billing, change accounts, purchase credits or resume another session. Authentication still uses the existing Claude installation and subscription, and usage shares its quota. Do not repeatedly retry quota errors.

A successful receipt requires a PASS without material findings, result metadata identifying exactly Opus 5.5, and unchanged selected file contents and modes. High effort is evidenced by the invocation, not independently attested by the result. If review fails, inspect `result.json` and the findings, revise the candidate, and use a new output directory. Preserve records outside active worktrees.

## Recheck before applying or pushing

```bash
python3 tools/agent-harness/review.py check \
  --root "$PWD" \
  --receipt /tmp/harness-review-unique/receipt.json
```

This verifies selected file hashes, modes and review artifacts. It does not stage, commit, push, merge or detect an omitted file. Compare the reviewed file list with the actual complete diff before publishing. Receipts are local audit records, not cryptographically signed approvals or a repository security boundary. Tests and code judgment still matter.

Use a separate clone or owned worktree when another agent is working. Pull `origin/main` before creating the branch and again before the final push. If main advanced, incorporate it without rewriting anyone else's work and re-review substantive changes. Never pull into another agent's dirty checkout. There is still a race between the last fetch and a remote update; record the main commit you verified.

## Render HTML

The renderer needs the packages in `requirements.txt` in an existing or isolated Python environment. These are tooling dependencies, not application requirements.

```bash
python3 tools/agent-harness/skills/html-review/scripts/render_review.py \
  --input docs/agents/review.md \
  --output docs/agents/review.html \
  --title 'Agent harness review' \
  --subtitle 'Rules, pinned skills and independent verification'
```

The output is standalone. Local file links require the original machine; use repository-relative links in published documents. The renderer strips executable source HTML but is intended for your own review documents, not as a general-purpose HTML security sanitizer.

## Validate locally

```bash
python3 -m unittest discover -s tools/agent-harness/tests -v
python3 tools/agent-harness/validate_skills.py
```

The skill check verifies the committed inventory hashes and required entry points. It does not prove every upstream workflow is correct. Existing global skills and instructions remain outside Git; checking out this branch does not modify them. Update a local installed copy only after comparing it with the version you reviewed here.
