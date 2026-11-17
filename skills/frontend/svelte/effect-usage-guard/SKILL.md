---
name: effect-usage-guard
description: >
  Review and avoid unnecessary Svelte $effect usage. Use when adding or editing effects, syncing UI with URL/query parameters, deriving state from props, stores or router state, or changing reactive side effects.
---

# Effect usage guard

## Outcome

Reactive state has explicit one-way ownership; every retained effect has a justified external purpose.

## Inputs

- Required: Component, state sources, and intended behavior.
- Optional: Ownership and lifecycle contracts.
- Default: Prefer URL-first or model-first state and no effect unless external boundary work requires it.

## Rules

- R1: Review in order: single source of truth, derived state, explicit event handler, two-way sync risk, then intentional external side effect; if any of the first three suffices, do not use an effect.
- R2: Prefer controlled components (`value` + `onChange`), one-way data flow, and explicit commands over local mirrors, hidden coupling, or internal synchronization loops.
- R3: Limit effects to external boundary work; require idempotence, feedback-loop and redundant-write guards, and teardown for subscriptions or other owned resources.

## Workflow

1. Identify the state owner and apply the ordered review in the reference before adding or retaining any `$effect`.
2. Use direct reads, `$derived`, or explicit click, submit, or navigation handlers whenever sufficient; remove mirrored mutable state.
3. Explicitly justify each remaining effect in reasoning: why derivation cannot work, why a handler is insufficient, and what prevents loops or redundant writes; stop and refactor if unjustified.
4. Check ownership, one-way flow, repeated execution, and teardown against the intended behavior; verify each retained effect is intentional external I/O, imperative integration, or subscription lifecycle work.

## Decisions

| Condition | Action |
|---|---|
| State owner or behavior is unclear | Inspect the request and existing state flow; ask only if materially ambiguous. |
| Optional lifecycle guidance is missing | Default to direct URL/model ownership and no effect; identify any boundary cleanup needs. |
| Review or behavior checks fail | Refactor to direct, derived, or handler-owned state; repair boundary guards and teardown where justified. |
| Justification or recovery fails | Stop effect-based work, report the blocker, and refactor away from unjustified effects. |

## Output

Return:
- Chosen state flow and effect changes.
- Ordered-review result, justification for each retained effect, and behavior-check results.
- Ownership, lifecycle, or verification limitations.

## Completion criteria

- No effect duplicates readable, derivable, or handler-owned state; controlled components preserve one-way flow.
- Every retained effect has explicit justification, intentional external work, idempotence, loop guards, and necessary teardown.

## References

- Read `references/review.md` when reviewing any proposed or existing effect.
