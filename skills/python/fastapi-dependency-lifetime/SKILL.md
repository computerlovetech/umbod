---
name: fastapi-dependency-lifetime
description: >
  Assign safe FastAPI dependency lifetimes and explicit composition. Use when changing routes, providers, services, repositories, adapters, app factories, lifespan setup, or API dependency injection.
---

# FastAPI dependency lifetime

## Outcome

Request operations use typed providers; only safe shared infrastructure lives in lifespan state.

## Inputs

- Required: Target objects, callers, and ownership or lifecycle requirements.
- Optional: Documented concurrency guarantees and existing provider chains.
- Default: Create operation objects per request; unclear concurrency safety never justifies sharing.

## Rules

- R1: Read the full guide before work; use the narrowest safe lifetime and its request-versus-lifespan classification.
- R2: Keep services, repositories, use cases, handlers, and dispatchers behind typed Depends providers, not app.state or api/main.py construction.
- R3: Reserve app.state for concurrency-safe, lifecycle-owned infrastructure; keep bounded-context provider chains explicit and main focused on assembly.

## Workflow

1. Read references/guide.md and inspect object creation, mutable/request state, consumers, and resource ownership.
2. Classify infrastructure and operation objects using the lifetime guide; require documented safety for concurrent sharing.
3. Compose request objects through typed bounded-context providers; inject lifespan infrastructure and use provider overrides in tests.
4. Apply every review-checklist question in the guide; verify creation sites, scope, app.state access, and test replacement seams.

## Decisions

| Condition | Action |
|---|---|
| Objects or lifetimes are unclear | Inspect the request, callers, and composition; ask only if materially ambiguous. |
| Optional input is missing | Apply the stated default and inspect existing code. |
| Validation fails | Move unsafe shared operation objects behind providers and repeat the lifetime review. |
| Recovery fails | Stop affected work and report the blocker; do not claim completion. |

## Output

Return:
- Changed provider, composition, and lifecycle paths.
- Lifetime checklist results and concurrency-safety evidence.
- Unresolved limitations or blockers.

## Completion criteria

- Operation objects are request-created by default and normal service resolution uses explicit providers.
- Shared resources have lifecycle ownership and documented concurrency safety; main remains assembly-only.

## References

- Read `references/guide.md` when starting any task covered by this skill; reading the full guide before work is mandatory.
- Read `references/guide.md` when object creation moves or test replacement requires its lifetime classification, provider pattern, and review checklist.
