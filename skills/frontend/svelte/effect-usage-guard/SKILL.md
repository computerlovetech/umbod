---
name: effect-usage-guard
description: Enforces critical review before introducing Svelte $effect. Use when writing or modifying code that includes $effect, reactive synchronization, URL-state sync, derived state, or side-effectful reactivity.
---

# Effect Usage Guard

## Purpose

Avoid unnecessary `$effect` usage and prefer explicit, deterministic state flows.

## When to Apply

Apply this skill whenever:
- You are about to add `$effect`.
- You are editing code that already uses `$effect`.
- The task involves syncing UI state with URL/query params.
- The task involves deriving state from props, stores, or router state.

## Required Reconsideration Checklist

Before keeping or adding `$effect`, answer these in order:

1. Is there a single source of truth you can read directly (for example `page.url`, props, or store state)?
2. Can this be expressed as derived state (`$derived`) instead of mirrored mutable state?
3. Can the change be handled in an explicit event handler (click/submit/navigation) instead of reactive side effects?
4. Would `$effect` introduce two-way sync or hidden coupling between states?
5. If `$effect` remains, is the side effect external and intentional (I/O, imperative API, subscription lifecycle)?

If 1-3 are true, do not use `$effect`.

## Best Practices

- Prefer URL-first or model-first state over duplicated local mirrors.
- Prefer controlled components (`value` + `onChange`) over internal sync loops.
- Prefer one-way data flow with explicit commands.
- Keep effects for boundary work only (imperative integration, subscriptions, teardown).
- Ensure effects are idempotent and guarded against feedback loops.

## Decision Rule

If an `$effect` is still necessary, briefly justify it in your reasoning with:
- Why it cannot be derived.
- Why an event handler is insufficient.
- What guard prevents loops or redundant writes.

If you cannot provide this justification, refactor away from `$effect`.
