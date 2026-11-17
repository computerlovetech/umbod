---
name: test-writing
description: >
  Guide writing and refactoring tests across pytest, Vitest, and Kind integration tests. Use when adding tests, changing fixtures or assertions, choosing test boundaries, or reviewing coverage and quality.
---

# Test writing

## Outcome

Tests prove observable behavior at the smallest suitable boundary with applicable verification completed.

## Inputs

- Required: Changed behavior, acceptance conditions, and affected test boundary.
- Optional: Existing tests, fixtures, timing data, and deployed-service risks.
- Default: Read only applicable references; choose the smallest boundary that proves behavior.

## Rules

- R1: Before writing or changing tests, identify behavior and boundary, then read the matching references; read multiple when applicable.
- R2: Add deployed integration coverage for real service wiring or cross-process risks, not duplicates of every unit scenario; DOM tests do not prove real-browser layout or deployed behavior.
- R3: Follow repository AGENTS.md verification requirements independently; a required suite does not imply every change needs a new integration test.

## Workflow

1. Identify acceptance conditions, changed behavior, existing coverage, and risks requiring deployed verification.
2. Read references/pytest.md for Python, references/vitest.md for TypeScript or JavaScript, and both references/kind-integration.md and references/pytest.md for Kind services.
3. Add or refactor behavior-focused tests using the relevant practices; for real-browser checks also load ../../../skills/other/agent-browser-ui-check/SKILL.md.
4. Run applicable repository checks; investigate failures and rerun after corrections, reporting any unresolved blocker.

## Decisions

| Condition | Action |
|---|---|
| Behavior or boundary is unclear | Clarify the acceptance condition before writing tests. |
| Multiple test boundaries apply | Read each matching reference and avoid redundant scenarios. |
| Real-browser evidence is needed | Use the agent-browser-ui-check skill; do not substitute DOM tests. |
| Verification fails | Investigate and repair, or report the blocker without claiming success. |

## Output

Return:
- Changed tests and the behavior they prove.
- Verification commands and observed results.
- Remaining coverage gaps or blocked checks.

## Completion criteria

- Tests cover acceptance behavior at appropriate boundaries and applicable verification passes.
- Deployed or browser risks are verified where needed; unresolved failures and limitations are explicit.

## References

- Read `references/pytest.md` when writing Python unit, adapter, contract, or in-process tests, or Kind service tests.
- Read `references/vitest.md` when writing TypeScript, JavaScript, reactive-state, or Svelte DOM tests.
- Read `references/kind-integration.md` when testing running services in a Kind cluster.
