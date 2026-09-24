---
name: python-domain-model-none-design
description: >-
  Use when writing or modifying Python dataclasses or Pydantic models that model
  domain data, DTOs, request/response objects, application state, or business
  concepts. Applies especially when fields, function arguments, or downstream
  branches use None, Optional, Union[..., None], or T | None.
---

# Python Domain Models Without Incidental None

## Core principle

Design domain data so values are present by the time they enter core logic. Treat uncertainty about missing values as an edge concern, not a core concern.

A `None` type in a dataclass, Pydantic model, or function argument is a design warning. It may be valid at an input boundary, but it must be justified. If it reaches core logic and causes branches such as `if value is None`, assume the model is probably hiding multiple states or an incomplete validation boundary.

## When to use

Use this skill when working on Python code that includes any of these:

- `@dataclass` models for domain data, DTOs, commands, queries, events, or state.
- Pydantic `BaseModel` classes for request, response, adapter, or domain-shaped data.
- Function or method arguments annotated as `Optional[...]`, `Union[..., None]`, `T | None`, or defaulted to `None`.
- Code that checks `is None` or `is not None` and then branches business logic.
- Refactors triggered by Semgrep warnings for None-able fields or arguments.

## Mandatory design review

Before adding or keeping a None-able type, answer these questions:

1. Is this value missing because raw user input, API input, config, file input, database data, or external service data is incomplete?
2. Is this value optional only at the boundary, but required for internal behavior?
3. Does `None` represent a meaningful state such as draft, anonymous, unauthenticated, unresolved, pending, deleted, unavailable, or not configured?
4. Does downstream code branch on `None` to choose different behavior?
5. Does a model contain many None-able fields that are only valid in some combinations?

If the answer to any question is yes, do not add another None check as the primary design. Redesign the data shape.

## Preferred resolutions

### Validate and normalize at the edge

For user input, API input, config, files, database rows, and external services:

- Accept missing values only in boundary-specific input models when necessary.
- Validate presence explicitly at that boundary.
- Convert boundary data into an internal model with required fields.
- Keep core services, domain functions, and internal DTOs free from incidental None types.

### Split models by lifecycle state

If `None` means the object is in a different lifecycle state, create separate models for those states.

Prefer distinct models named from the state or use case, such as request, draft, validated, resolved, persisted, authenticated, unauthenticated, scheduled, completed, or failed.

Do not keep one broad model with many None-able fields when only some fields are valid together.

### Replace None branches with explicit polymorphism or result types

If behavior changes based on whether a field is None:

- Move the branch to the boundary and call the correct core operation.
- Split the input into separate command/query/DTO types.
- Use explicit result or state objects that name the condition.
- Prefer domain vocabulary over presence checks.

### Keep absence local

When absence is unavoidable, keep it close to the source:

- Adapter code may translate missing external data into validation errors or explicit states.
- API route code may reject incomplete requests before calling application services.
- Repository lookup methods may model not-found results explicitly at the port boundary.
- Core logic should receive the state it needs without repeated None checks.

## Red flags

Treat these as design smells:

- A dataclass or Pydantic model with several None-able fields.
- A field that is None only before validation, persistence, enrichment, or authentication.
- Business rules that start by checking whether a required-looking value is None.
- Functions that accept None because callers have not validated their inputs.
- A single model reused for create, update, persisted, response, and internal domain logic.
- Comments or names implying a field is present after some step while the type still allows None.

## Acceptable exceptions

None may be acceptable when it is deliberate and contained:

- A boundary input type represents a genuinely optional user-supplied field.
- A port method models absence from a lookup and the caller handles that absence immediately.
- An adapter mirrors an external wire format before validation or mapping.
- A framework requires a None default and the value is normalized before entering core logic.

Even in these cases, prefer naming the boundary model clearly and prevent the None-able type from spreading into internal core models.

## Checklist before finishing

- [ ] Every None-able annotation has an explicit boundary or state-modeling reason.
- [ ] Missing user or external input is validated before core logic is called.
- [ ] Internal dataclasses and Pydantic models assume required values are present.
- [ ] Repeated `is None` branches have been replaced by explicit DTOs, states, or boundary validation.
- [ ] Broad models with many None-able fields have been considered for splitting.
- [ ] Function and method arguments in core services do not accept None unless absence is the explicit operation being modeled.

## Relation to other skills

- Use `ports-adapters-io` when None originates from network, file, database, or external-service I/O.
- Use `fastapi-dependency-lifetime` when validation or normalization belongs in FastAPI routes or dependencies.
- Use `python-test-practices` when adding regression tests for redesigned model states.
