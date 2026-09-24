---
name: atdd-write-acceptance-tests
description: ATDD step 4. Write executable acceptance tests against the approved testable interface before implementation. Use after step 3 is ready.
disable-model-invocation: true
---

# ATDD Write Acceptance Tests

## Use When
`03-testable-interface.md` exists with `Ready For Acceptance Test Writing: Yes`.

## Inputs
- `01` through `03` artifacts
- [references/four-layer-acceptance-testing.md](references/four-layer-acceptance-testing.md), [references/executable-specifications.md](references/executable-specifications.md) when test structure is unclear
- If missing: use earlier ATDD step skills

## Do
- Write test cases calling approved DSL; protocol drivers in test/support code
- Follow existing project test conventions; ask before introducing new structure
- Map every scenario to a test or defer with reason
- Run test command; record red-run result

## Write
- `.atdd/features/<slug>/04-acceptance-test-plan.md` — [assets/artifact-template.md](assets/artifact-template.md)
- Acceptance test files in project's existing acceptance/integration/e2e location

## Rules
- Protocol drivers, DSL implementations, harness factories, fakes, and acceptance-only DTOs live under test/support directories
- Protocol drivers may drive public production interfaces, but production source must never expose acceptance-specific modules or factories
- Tests express what, not how; one atomic test per scenario slice
- Do not implement production behavior
- Red run: Fails as expected | Fails unexpectedly (fix setup) | Passes unexpectedly (stop, reassess) | Not run (explain)

## Done
- Tests and plan exist; command and red-run evidence documented
- Next step: `atdd-implementation-loop`
