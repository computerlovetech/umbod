---
name: reusable-components
description: >
  Define cohesive reusable UI boundaries and maintain the component index. Use when creating, changing, extracting, reviewing, moving, renaming, or deleting reusable frontend components or shared styling.
---

# Reusable components

## Outcome

Reuse boundaries are evidence-based and the component index stays accurate.

## Inputs

- Required: Target components, consumers, and intended change.
- Optional: Existing reuse rationale and compatibility constraints.
- Default: Inspect real consumers; do not assume reuse from similarity or import counts.

## Rules

- R1: Read the full guide before work; follow its REP, CCP, CRP, actor-ownership, and index obligations.
- R2: Maintain umbod/frontend/COMPONENT_INDEX.md in the same change; preserve metadata, concise links, limits, and discovery.
- R3: Keep repository paths repository-root-relative; resolve bundled scripts and requirements from this skill directory.

## Workflow

1. Read references/guide.md, the component index, linked sources, real consumers, and ADR-007; load write-module-readme and applicable Svelte/state skills.
2. Compare reuse alternatives; state consumers, REP/CCP/CRP evidence, priorities, trade-offs, and the include/exclude/split/defer decision.
3. Implement the chosen boundary and update index eligibility, descriptions, affected links, and stale entries.
4. Run the guide's check_component_index.py command after component additions/deletions/moves/renames or index edits; manually check coverage and run applicable README, UI, or checker checks.

## Decisions

| Condition | Action |
|---|---|
| Target or change is unclear | Inspect the request, workspace, and consumers; ask only if materially ambiguous. |
| Optional input is missing | Apply the stated default and inspect existing code. |
| Validation fails | Fix links or boundaries and rerun; never add placeholders or discard valid entries to silence checks. |
| Recovery fails | Stop affected work and report the blocker; do not claim completion. |

## Output

Return:
- Changed components, index paths, and concise reuse decision.
- Dead-link checker and applicable verification results.
- Unresolved limitations or blockers.

## Completion criteria

- REP, CCP, CRP and actor boundaries are assessed against source and consumers.
- Index maintenance and required checks are complete; limits and unresolved evidence are reported.

## References

- Read `references/guide.md` when starting any task covered by this skill; reading the full guide before work is mandatory.
- Read `references/guide.md` when index or implementation work requires write-module-readme, applicable Svelte/state skills, or conditional README, UI, and checker verification.
