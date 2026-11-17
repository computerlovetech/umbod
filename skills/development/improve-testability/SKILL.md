---
name: improve-testability
description: >
  Review bounded test batches through isolated public interfaces. Use when the user explicitly invokes testability cleanup or approved seam refactoring.
disable-model-invocation: true
---

# Improve Testability

## Outcome

One batch preserves behavior, case coverage, and isolation through supported public boundaries, with missing seams reported.

## Inputs

- Required: Explicit user invocation and an identifiable source area and test suite.
- Optional: Selected paths, batch size, previous reports, and approved production refactors.
- Default: Review three test files or equivalent suite units; stop after the batch report.

## Rules

- R1: Run only on explicit user invocation; preserve unrelated work and never stage, commit, or revert it.
- R2: Test cleanup does not authorize production refactoring; obtain explicit approval before changing production architecture or interfaces.
- R3: Preserve coverage, parametrized cases, isolation, resource ownership, and cleanup; report exact before/after case counts.

## Workflow

1. Read references/guide.md fully before working; establish scope, instructions, source boundaries, and baseline commands/results.
2. Inspect every selected test and corresponding source; identify coupling and choose the narrowest supported public boundary.
3. Rewrite only within authorization, keeping behavior real and faking external boundaries; report missing seams rather than broadening the unit.
4. Run focused before/after tests and applicable repository checks from the required directory; review the actual diff and report failures and retries.

## Decisions

| Condition | Action |
|---|---|
| Explicit invocation or scope is missing | Do not activate automatically; ask for authorization or the unclear scope. |
| Paths or batch size are omitted | Select three units within the established scope, avoiding previous batches. |
| Verification fails or a seam is missing | Inspect evidence, retain focused coverage, and request approval for production changes. |
| Recovery remains blocked | Stop and report retained coupling, failed checks, and unresolved risks. |

## Output

Return:
- Batch scope, paths, boundaries, removed/retained coupling, and refactor recommendations versus approved changes.
- Actual check outcomes, isolation and coverage evidence, case-count deltas, skips, retries, and mutation findings when used.
- Unresolved limitations and confirmation unrelated work was preserved; stop until another batch is requested.

## Completion criteria

- The selected batch preserves observable behavior and isolation without unapproved production refactoring.
- The report records actual verification and case counts without claiming the entire suite was reviewed.

## References

- Read `references/guide.md` when explicitly invoked, before any task work; it contains the mandatory full procedure.
- Read `references/mutation-testing.md` when bounded mutation feedback is warranted by the guide.
