---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
---

## Local Codex integration

This is a local adaptation, not an official Codex release. See `SOURCE.json` for the pinned upstream and modifications.
Use available Codex tools; a request to read another skill means read its local `SKILL.md`, not call a nonexistent Skill tool. User instructions and the current authorized task take precedence. Skills do not authorize commits, publication, paid model calls, deployments or broader work. Use the inherited model; delegate only when the user or applicable active instructions authorize it. For material the user is asked to review, use `html-review` and provide the HTML link.

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle: consult them before and during the loop, not after.

When exploring the codebase, read `GLOSSARY.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification: "user can checkout with valid cart" tells you exactly what capability exists, and it survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams: where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Choose tests at the relevant public interface.** Reuse interfaces and acceptance criteria already established by the task or repository. State what the test catches and proceed within the authorized scope. Ask only when the choice would materially change product behavior, scope or cost. For persistence and transaction contracts, inspecting a real disposable database can be the correct observation point; do not replace it with a mock just to avoid database inspection.

State the chosen public interface and what the test catches. Routine test placement does not need a separate approval.

When the shape of that interface is itself in question (how deep the module is, where the seam belongs, what the interface should expose), read the `codebase-design` skill for the vocabulary. It is the shared source of the module, interface, depth, seam, adapter, leverage and locality terms, and it is a reference to consult, not a session to run.

## Anti-patterns

- **Implementation-coupled**: mocks internal collaborators, tests private methods, or verifies an irrelevant internal side effect instead of the contractual outcome. The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological**: the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth: a known-good literal, a worked example, the spec.
- **Horizontal slicing**: writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead: one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- Refactor only after green and only within the requested scope. Re-run affected checks. Use the available engineering code-review skill for substantial changes.
