---
name: create-state-class
description: >
  Encapsulate cohesive Svelte reactive state in dedicated state classes. Use when creating or modifying component state, adding reactive variables, refactoring component logic, or managing Svelte state.
---

# Create State Class

## Outcome

Cohesive state classes own reactive values and mutations while components stay declarative.

## Inputs

- Required: Target component, state concerns, and intended behavior.
- Optional: Existing state classes and caller constraints.
- Default: Use one class per cohesive state concern in a separate .svelte.ts module.

## Rules

- R1: Read the full guide before work; apply its ownership rules to mutable state and derived values.
- R2: Keep all mutations behind named class methods; read properties directly and prefer arrow methods for callback binding.
- R3: Never define inline state classes or loose component state; use svelte/reactivity versions of Set, Map, Date, and URL.

## Workflow

1. Read references/guide.md and inspect state ownership, consumers, initial values, and mutations.
2. Define or extend exported .svelte.ts state classes; keep unrelated concerns separate and avoid trivial getters.
3. Import and instantiate classes in components; route writes through methods and preserve callback binding.
4. Review the guide's rules and anti-patterns; use .cursor/hooks/check-state-class.ts if available. If absent, report that automated check as unavailable without blocking work solely on its absence.

## Decisions

| Condition | Action |
|---|---|
| Target or behavior is unclear | Inspect the request and workspace; ask only if material ambiguity remains. |
| Optional input is missing | Apply the stated default and inspect existing code. |
| Review or an available check finds violations | Fix ownership, placement, or mutation issues and repeat the review or check. |
| Recovery fails | Stop affected work and report the blocker; do not claim completion. |

## Output

Return:
- Changed .svelte.ts classes and component integration paths.
- Compliance check and ownership review results.
- Unresolved limitations or blockers.

## Completion criteria

- All mutable and derived state follows cohesive class ownership with method-only writes.
- Classes live outside .svelte files; callback binding and compliance verification are accounted for.

## References

- Read `references/guide.md` when starting any task covered by this skill; reading the full guide before work is mandatory.
- Read `references/guide.md` when prop or external data initialization, callback binding, or built-in collections require its constructor, binding, and reactive-class guidance.
