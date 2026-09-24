---
name: atdd-identify-scenarios
description: ATDD step 2. Derive Given/When/Then acceptance scenarios from a clarified feature. Use after step 1 is ready; before interface design or tests.
disable-model-invocation: true
---

# ATDD Identify Scenarios

## Use When
`01-clarified-feature.md` exists with `Ready For Scenario Discovery: Yes`.

## Inputs
- `.atdd/features/<slug>/01-clarified-feature.md`
- If scenario format is unclear: [references/given-when-then.md](references/given-when-then.md), [references/atdd-terms.md](references/atdd-terms.md)
- If missing or not ready: use `atdd-clarify-feature` first

## Do
- Cover in-scope behavior with observable Given/When/Then scenarios
- Group: happy path, edge cases, errors, permissions, state/data
- Exclude out-of-scope scenarios with reasons
- Use question format from [assets/artifact-template.md](assets/artifact-template.md) for unresolved stakeholder decisions
- Do not write tests, design interfaces, or implement

## Write
`.atdd/features/<slug>/02-acceptance-scenarios.md` — [assets/artifact-template.md](assets/artifact-template.md)

## Rules
- Scenarios use declarative, observable language only
- Preserve clarified boundaries from step 1

## Done
- Every in-scope scenario mapped or deferred
- `Ready For Testable Interface Design` is Yes, or blockers documented
- Next step: `atdd-design-testable-interface` when ready
