---
name: atdd-clarify-feature
description: ATDD step 1. Clarify vague feature intent into a scoped artifact before scenario discovery. Use when actors, goals, boundaries, or outcomes are ambiguous.
disable-model-invocation: true
---

# ATDD Clarify Feature

## Use When
Starting from a vague idea, unclear request, or before scenario discovery.

## Inputs
- User feature idea or request
- If terminology is unfamiliar: [references/atdd-terms.md](references/atdd-terms.md), [references/specification-by-example.md](references/specification-by-example.md)

## Do
- Run Explorer subagent: search `.atdd/` and codebase for related actors, domain language, prior decisions, and gaps
- Ask one focused question at a time until feature scope is clear
- Use question format from [assets/artifact-template.md](assets/artifact-template.md)
- Do not write scenarios, tests, or code

## Write
`.atdd/features/<slug>/01-clarified-feature.md` — [assets/artifact-template.md](assets/artifact-template.md)

## Rules
- Focus clarification on gaps not already known
- Set `Ready For Scenario Discovery` to Yes only when user-resolvable ambiguities are closed

## Done
- Artifact exists or shown to user
- Next step: `atdd-identify-scenarios` when ready
