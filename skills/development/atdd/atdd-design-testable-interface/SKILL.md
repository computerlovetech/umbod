---
name: atdd-design-testable-interface
description: ATDD step 3. Design DSL plus protocol drivers as the acceptance-test boundary. Use after scenarios are ready; before writing tests.
disable-model-invocation: true
---

# ATDD Design Testable Interface

## Use When
`02-acceptance-scenarios.md` exists with `Ready For Testable Interface Design: Yes`.

## Inputs
- `01-clarified-feature.md`, `02-acceptance-scenarios.md`
- [references/four-layer-acceptance-testing.md](references/four-layer-acceptance-testing.md), [references/given-when-then.md](references/given-when-then.md) when model is unclear
- If missing or not ready: use `atdd-identify-scenarios` first

## Do
- Run Explorer subagent: find existing DSL, drivers, fixtures to reuse; identify only missing testable surface
- Design DSL (what) and one protocol driver per public channel (how)
- Propose interface in code; ask one focused approval question; iterate until approved
- Run heuristic check: substitutability, non-technical readability, what-not-how, public interfaces only
- Do not write tests or implement production behavior

## Write
`.atdd/features/<slug>/03-testable-interface.md` — [assets/artifact-template.md](assets/artifact-template.md)

## Rules
- Testable interface is not a production API
- DSL expresses domain operations; drivers hold all channel/infrastructure knowledge
- Reach SUT only through public interfaces

## Done
- User approved DSL + drivers in session
- Scenarios mapped to DSL operations
- `Ready For Acceptance Test Writing` is Yes, or blockers documented
- Next step: `atdd-write-acceptance-tests` when ready
