---
name: ports-adapters-io
description: >
  Applies hexagonal (ports and adapters) design for I/O boundaries—network,
  files, databases—so the core stays independent of infrastructure. Use when the
  user mentions ports and adapters, hexagonal architecture,
  or any implementations for external I/O.
---

# Ports and Adapters for I/O

## Outcome

The core depends on validated domain ports with swappable I/O adapters and fast contract tests.

## Inputs

- Required: I/O operation, domain contract, and observable success and failure behavior.
- Optional: Existing ports, adapters, and application composition.
- Default: Define the port first and implement an in-memory adapter before or alongside real I/O.

## Rules

- R1: Read references/guide.md completely before applying; follow its mandatory workflow and finishing checklist.
- R2: Keep concrete drivers out of the core; adapters validate boundary data with Pydantic or Zod and expose domain contracts.
- R3: Test behavior through the port using in-memory adapters; keep test-only adapters in tests, never production source or exports without an actual runtime consumer.

## Workflow

1. Read the detailed guide; define the domain port before concrete I/O and inspect existing composition.
2. Define validated inputs and outputs and implement the in-memory adapter using the same contracts.
3. Implement and inject the real adapter; use the linked API client skill for HTTP clients.
4. Run public port-contract tests and narrow infrastructure adapter tests; verify the guide's finishing checklist.

## Decisions

| Condition | Action |
|---|---|
| Domain operation or contract is unclear | Inspect the request and existing code; ask only if material ambiguity remains. |
| Existing adapters are absent | Apply the port-first, in-memory-first default. |
| Validation or contract tests fail | Repair boundary mapping or adapter behavior and rerun tests. |
| Recovery fails | Stop the affected I/O work and report the blocker. |

## Output

Return:
- Port, model, adapter, test, and composition paths.
- Contract-test results and finishing checklist findings.
- Unresolved boundary or runtime-placement limitations.

## Completion criteria

- The core imports ports rather than concrete drivers; invalid data fails at the edge.
- In-memory contract tests pass and test-only adapters stay outside production dependencies.

## References

- Read `references/guide.md` when applying this skill; its workflow and checklist are mandatory. Command paths remain skill-root-relative unless stated otherwise.
