# Harness verification receipt

**PASS. Opus reported no material findings for the 71 supplied files.**

[Open the harness overview](review.html) or inspect the [complete file hashes and receipt](verification.json).

## Review identity

- Requested model: `claude-opus-5-5`.
- Returned canonical model: `claude-opus-5-5`, first-party provider.
- Requested effort: `high`. The invocation records this setting; returned metadata does not independently attest internal effort.
- Final main pull before commit and push: `git pull --ff-only origin main`, already up to date at `e9506fc6eb513173c412f4cd2631111aff3cd3ab`.
- Work prepared in a separate clone, with the reviewer in a new tool-disabled session outside it. Existing Claude worktrees were left alone.

## Observed local checks

Five offline test methods passed. All twelve complete skill inventories and twelve skill entry-point validations passed. Headless Chromium checks at 1440px and 390px found no document overflow, broken navigation anchors, external assets or browser errors. Print output was generated. Markdown text was preserved in the HTML and relative evidence links existed. Application tests were not run because this branch changes no application code.

## Reviewer scope and limitations

Static review of the supplied packet only: AGENTS.md (main plus the appended Agent harness section), docs/agents/*, tools/agent-harness/{README.md, requirements.txt, review.py, validate_skills.py, tests/test_review.py} and all twelve skill directories. Checked review.py's control flow: path and symlink rejection, size limits, UTF-8 decoding, removal of API-billing env vars, the subscription auth gate before any model call, exact modelUsage set equality, the PASS plus empty material_findings requirement, the post-review content and mode recheck, and check() re-validation of result, packet, candidate and invocation hashes. All of these fail closed. Checked that the tests exercise these paths as described. Checked validate_skills.py's set-equality inventory logic and spot-checked skills-lock.json file hashes against the supplied per-file sha256 values (codebase-design, pstack-how, tdd/tests.md, to-tickets, html-review CSS and renderer); all matched. Compared review.html text, headings, nav, tables and links against review.md; they correspond. Checked render_review.py's allowlist sanitization and URL-scheme handling against its documented non-general-sanitizer scope. Checked docs for consistency with runner behavior, authorization limits and the no-install, no-app-change scope. Limitations: I did not execute any code, tests, the renderer, a browser or the Claude CLI. The claimed test, validation, browser and hash results are taken from task_context, not reproduced. I cannot verify upstream fidelity, the upstream_skill_sha256 values, license texts, or CLI flag support beyond the fact that this session was evidently launched. I cannot attest the effort level applied to this session. The receipt is treated as a trust-based local audit aid, per documented scope. The pre-existing AGENTS.md 'No build tools' contradiction was not assessed, per instructions.

## Optional reviewer observations

These were not classified as material findings. They remain useful follow-up work, including the limits of safe-mode isolation and portability.

1. Observed in this reviewer session: '--permission-mode plan' injected plan-mode system instructions telling the model to write a plan file and end the turn with ExitPlanMode. That conflicts with the JSON-only output contract. Tools were unavailable, so no action was possible, and a non-JSON reply would fail closed. Still, it risks spurious PENDING results. With '--tools ""' already set, consider whether plan mode is needed. The session context also included user-level details (an account email and an additional working directory under ~/.claude/projects), so 'disables customizations' may overstate the isolation.

2. review.py validate_result: if result.json or the inner verdict decodes to a JSON value that is not an object (for example a string or list), .get raises AttributeError. main() does not catch AttributeError, so the run exits with a traceback rather than 'PENDING VERIFICATION'. It still fails closed. Adding isinstance(dict) checks would give a cleaner message.

3. Models often wrap JSON in code fences despite instructions. json.loads would then reject an otherwise valid PASS. This fails safe but may cause avoidable re-runs; consider documenting or tolerating a single fenced block.

4. Portability: read_text and write_text and subprocess text mode use the locale encoding. On non-UTF-8 locales, a non-ASCII context file could make the packet.txt bytes differ from digest(prompt.encode()), so check() would then fail. Passing encoding='utf-8' explicitly would make this deterministic. The same applies to render_review.py output, which declares charset utf-8.

5. The tests ran only on Python 3.14, while the docs state 3.10+ support. No 3.11+-only APIs were spotted, but 3.10 compatibility is asserted rather than tested.

6. render_review.py's bold-to-heading promotion applies to any line that starts and ends with '**', including lines inside fenced code blocks and lines like '**A** text **B**'. This can silently alter source content. It did not affect review.md.

7. validate_skills.py hashes every file under each skill directory, so a stray macOS .DS_Store would fail validation. That is fail-closed but may be confusing.

8. Residual upstream references with no local target: to-spec step 3 and its frontmatter still say 'publish ... apply ready-for-agent'. to-tickets references '/setup-matt-pocock-skills'. pstack-blast-radius references 'how'/'why' and requires 'unslop' unconditionally. pstack-benchmark-checklist references Perf issue and Hillclimb playbooks. grill-with-docs says 'installed' SKILL.md. The preambles and issue-tracker.md mostly neutralize these, but small wording fixes would reduce ambiguity.

9. domain.md points to docs/listing-trust-2026-10-10/, which is explicitly excluded from this branch. The 'in the relevant worktree' qualifier helps, but readers of main will find no such path.

10. Several docs and the html-review skill refer to Umar with he/his. The user has not stated their pronouns, so consider using the name or 'they' instead.

## Record handling

The JSON receipt preserves the reviewed content hashes, verdict and limitations. Raw prompts, session metadata and local account information are kept outside the repository. The receipt and this rendering do not add a new engineering change and are exempt from recursive review under the standing rule.
