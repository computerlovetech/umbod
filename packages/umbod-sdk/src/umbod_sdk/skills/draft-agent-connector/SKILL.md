---
name: draft-agent-connector
description: >
  Author and test Umbod connectors. Use when drafting or editing a portable single-file connector or a trusted Pydantic plugin.
---

# Draft Agent Connector

## Outcome

A connector in the requested format, with passing offline tests.

## Inputs

- Required: Connector format and the tools or behavior the user wants.
- Optional: Existing source, upstream API contract, and redacted response fixtures.
- Default: Preserve the format of an existing connector when the user is not asking to migrate it.

## Rules

- R1: Confirm the format before opening a reference; do not ask again if the request already answers it.
- R2: Never ask for secrets or run tests against a live API.
- R3: Stop at authoring and offline verification; do not change packaging, deployment, or runtime wiring.

## Workflow

1. Use the request and existing source to identify the format and API needs. If the format is unclear, ask: "Are you authoring a portable single-file connector or a trusted installed plugin?" If a portable connector's API needs are unclear, ask: "Will it call an external API to read, write, or both, or does it work without HTTP?" Wait for the missing answer before reading references.
2. Open only the applicable references below. For portable HTTP, read both portable references; for a trusted plugin with its own HTTP client, read only the trusted reference.
3. Confirm the wanted tools and upstream contracts before implementing the requested behavior.
4. Run the connector's offline tests using pytest and report what passed.

## Decisions

| Condition | Action |
|---|---|
| The user is unsure about the format | Explain that portable is a single file with explicit schemas and offline-only HTTP today. For live Umbod execution, choose a trusted installed Pydantic plugin with its own client. Ask which they need. |
| A portable connector does not call an API | Read only the portable connector reference. |
| A test fails | Fix the connector or its offline fixture, then rerun the tests. |
| An upstream contract cannot be confirmed | Report the missing information; do not invent endpoints or fields. |

## Output

Return:
- Connector and test file paths.
- Offline verification results.
- Unresolved contract gaps or runtime limitations.

## Completion criteria

- The connector matches the selected authoring format and requested tools.
- Its offline tests pass without credentials or network access, or the blocker is reported.

## References

- Read `references/portable-connector.md` when authoring a single-file connector with explicit JSON schemas.
- Read `references/portable-http.md` when a portable connector needs GET, POST, or an HTTP configuration check.
- Read `references/trusted-plugin.md` when authoring or editing an installed Pydantic plugin.
