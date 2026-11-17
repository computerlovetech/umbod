---
name: python-domain-model-none-design
description: >
  Model Python domain states without incidental None. Use when changing dataclasses, Pydantic models, DTOs, request/response data, application state, optional arguments, None branches, or related Semgrep findings.
---

# Python Domain Models Without Incidental None

## Outcome

Boundary validation and explicit domain states keep incidental absence out of core logic.

## Inputs

- Required: Target models or arguments, callers, and domain meaning of absence.
- Optional: Wire-format constraints and regression scenarios.
- Default: Treat None-able types as design warnings; require values before core logic.

## Rules

- R1: Read the full guide before work; answer all mandatory design-review questions before adding or retaining None-able types.
- R2: Validate and normalize at boundaries; split lifecycle states or use explicit result types and polymorphism rather than repeated presence branches.
- R3: Keep justified absence local to input, ports, adapters, or framework boundaries; never spread broad partially valid models into core logic.

## Workflow

1. Read references/guide.md; trace missing values from source through models, arguments, and downstream business branches.
2. Apply all five design-review questions; redesign shapes when any answer is yes rather than adding another None check.
3. Normalize boundary input or introduce explicit commands, results, and lifecycle models; justify each contained exception.
4. Complete every finishing-checklist item; inspect core arguments and None branches, and use test-writing plus its pytest reference when adding regression tests.

## Decisions

| Condition | Action |
|---|---|
| Models or absence semantics are unclear | Inspect the request and callers; ask only if material ambiguity remains. |
| Optional input is missing | Apply the stated default and inspect existing code. |
| Validation fails | Revisit validation boundaries or state shapes and repeat the finishing checklist. |
| Recovery fails | Stop affected work and report the blocker; do not claim completion. |

## Output

Return:
- Changed model and boundary paths with absence-modeling decisions.
- Design-review and finishing-checklist results.
- Unresolved limitations or blockers.

## Completion criteria

- Each None-able annotation has a justified boundary or explicit state-modeling reason.
- Required values reach core logic validated; repeated branches and broad partial models are addressed.

## References

- Read `references/guide.md` when starting any task covered by this skill; reading the full guide before work is mandatory.
- Read `references/guide.md` when I/O requires ports-adapters-io, FastAPI normalization requires fastapi-dependency-lifetime, or regression tests require test-writing and its pytest reference.
