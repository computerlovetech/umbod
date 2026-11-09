# ADR-015: Self-Describing Built-In MCP Tool Contracts

- **Status:** Accepted
- **Date:** 2026-11-09
- **Status changed:** 2026-11-09
- **Scope:** Existing and future built-in MCP tools; connector-provided tool adoption is deferred

## Decision

Make built-in tool contracts self-describing: **agents discover how to construct a valid call rather than learn through avoidable failures.** Judge this contract by the discovery information the agent actually receives, not only by server-side schema validity.

This supplements [ADR-014](ADR-014-built-in-mcp-response-guidance.md), which governs built-in responses and recovery guidance, without replacing its accepted decision or changing [ADR-008](ADR-008-event-synchronized-tool-runtime.md)'s discovery runtime.

- Publish complete nested input shapes, discriminators, required fields, bounds, and field meanings. After reference resolution, each operation branch must describe its own inputs without depending on parent or sibling constraints to supply missing types. Do not expose known structured inputs as unrestricted objects, `any`, or `unknown`; intentionally freeform fields remain explicit maps.
- Express rules as machine-readable constraints where they faithfully describe runtime behavior. Describe normalization, omission, empty-value meanings, cross-field requirements, and rules that cannot be represented faithfully. Discovery and runtime validation must not contradict each other.
- Keep essential calling instructions in agent-visible tool or field descriptions when clients omit schema-level descriptions or unsupported keywords. Deliberate repetition is acceptable for compatibility, but must remain consistent with the authoritative domain rules. Do not require source inspection, private metadata, or a failed invocation to discover required arguments.
- Verify the published MCP discovery descriptors and client-rendered declarations. Valid JSON Schema alone is insufficient. Cover valid and invalid inputs, nested operation variants, and preservation of essential guidance; treat loss of structured input types or required guidance as a regression.

Runtime validation, authorization, confirmation, and current-state checks remain authoritative. A well-formed call can still fail because of permissions, stale revisions, service availability, or other facts that discovery cannot guarantee. Follow ADR-014 for those outcomes; do not expose hidden resources or sensitive values to make discovery more helpful.

## Context and rationale

The filesystem browse tool exposed a valid schema with a structured target at the root but unrestricted targets inside its operation branches. Pi's declaration renderer retained the branches without the root constraint, so the agent saw an opaque target and made two invalid calls before discovering its required structure.

The audit also found input rules enforced only at runtime and unexplained metadata values. Subsequent rendering checks showed that a root schema description could disappear even while field types survived. These observations establish that server validation and agent usability are distinct boundaries. Discoverable types and concise instructions reduce avoidable calls without weakening execution checks.

## Alternatives considered

- **Retain validation-driven discovery:** less schema maintenance, but forces agents to probe predictable input rules and can waste calls on tools with side effects.
- **Rely on valid schemas and tool prose alone:** keeps one formal contract, but root constraints can disappear during rendering, while prose alone does not provide reliable nested argument types. Retain both structured schemas and essential visible guidance.
- **Extend ADR-014 in place:** keeps built-in guidance together, but changes an accepted response-focused record. Use a companion decision for discovery and inputs while preserving ADR-014.

## Consequences

Built-in tool changes require compatibility checks at both discovery and rendering boundaries. Some schema structure and guidance may be repeated, increasing maintenance and context cost; keep repetition focused and test against drift. Changes to schema generation or client rendering can regress usability without changing runtime behavior.

This record does not establish compliance for every built-in tool or extend the requirement to connector-provided tools. Existing filesystem coverage is evidence for the principle, not a universal client compatibility guarantee.

## Confidence and reevaluation

The filesystem regression and Pi rendering checks support this decision; a cross-client compatibility matrix has not been established. Connector adoption remains open. Reevaluate through a new ADR if supported clients cannot retain required types and guidance, or if compatibility duplication becomes impractical.

## Supporting material

- [Filesystem discovery tests](../../api/tests/umbod/mcp/filesystem/test_tools.py) — Published contracts across all 13 filesystem tools.
- [Browse discovery tests](../../api/tests/umbod/mcp/filesystem/test_browsing.py) — Independently usable operation branches and target variants.
- [Browse input schemas](../../api/src/umbod/mcp/filesystem/browsing_models.py) — Typed operation inputs and schema publication.
- [Node update tool](../../api/src/umbod/mcp/filesystem/update.py) — Essential update requirements in the tool description.
