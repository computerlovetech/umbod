---
name: api-client-architecture
description: >
  Enforces Zod-validated HTTP clients split by bounded context (transport port,
  route adapters, composite API). Use when adding or modifying fetch-based
  clients or infrastructure/ API code. For ports-and-adapters workflow and
  in-memory-first testing, see ports-adapters-io.
---

# API Client Architecture

## Outcome

HTTP clients validate every network boundary and separate bounded contexts behind a transport port.

## Inputs

- Required: Client change, affected wire contracts, and caller context.
- Optional: Existing transport, route adapters, schemas, and compatibility needs.
- Default: Use Zod schemas, a transport port, resource routes, and one composite client.

## Rules

- R1: Read references/guide.md completely before applying; follow its architecture, checklist, and test requirements.
- R2: Validate outbound and inbound payloads with separate domain Zod schemas; infer types, normalize backend nulls, and surface directional SchemaValidationError failures.
- R3: Split resource routes by bounded context over an injected transport; follow ports-adapters-io for port-first design, in-memory adapters, and contract tests.

## Workflow

1. Read the detailed guide and linked ports-adapters-io skill; inspect affected contracts and existing clients.
2. Define domain schemas and the transport port; provide the in-memory adapter before or alongside real I/O.
3. Implement resource routes and composite wiring; keep validation and error mapping in the transport.
4. Run the guide's transport, route-contract, and null-normalization tests; review every implementation checklist item.

## Decisions

| Condition | Action |
|---|---|
| Contract or caller context is unclear | Inspect the request and existing code; ask only if material ambiguity remains. |
| Existing architecture is absent | Apply the four-part default layout from the guide. |
| Validation or contract tests fail | Repair schemas, boundary validation, or route isolation and rerun. |
| Recovery fails | Stop the affected change and report the failing contract and blocker. |

## Output

Return:
- Changed schema, transport, route, and composite paths.
- Test results and implementation checklist findings.
- Unresolved contract or compatibility limitations.

## Completion criteria

- All wire payloads pass Zod boundary validation; routes remain resource-specific.
- Port-contract tests and every applicable guide checklist item pass.

## References

- Read `references/guide.md` when applying this skill; it is mandatory detailed guidance. Command paths remain skill-root-relative unless stated otherwise.
