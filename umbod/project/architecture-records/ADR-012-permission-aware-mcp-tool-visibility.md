# ADR-012: Show Only MCP Tools With an Authorized Operation

- **Status:** Proposed
- **Date:** 2026-11-01
- **Scope:** All Umbod MCP tool discovery and exposure paths

## Decision

Expose an MCP tool to a user's agent only when that caller is authorized to perform at least one operation supported by the tool. Hide the tool when no supported operation is authorized. Apply this principle consistently to filesystem tools, administrator tools, and connector tools, including listing, search, code-mode discovery, and connector-scoped discovery.

For a tool with multiple operations, permission for any one operation is sufficient for visibility; permission for every operation is not required. Visibility does not authorize the other operations or every resource accepted by the tool. Where authority is resource-specific, eligibility means at least one supported operation on a resource the caller is allowed to use, not access to all resources or their ancestors.

Discovery uses the caller's effective authority in the requested endpoint scope, not merely authentication, tool registration, or an unrelated administrator role. If eligibility cannot be established safely, do not expose the affected tool. Endpoint scope, publication, and availability restrictions continue to apply; this rule does not make an otherwise unavailable tool visible.

Every invocation must separately authorize the requested operation and resource against current authority. Calling a known tool name, retaining a previously discovered tool, or obtaining an approval must not bypass this check.

## Context and rationale

The investigation found that administrator tools check the caller's configured membership during discovery, while filesystem tool visibility checks only that the request is not connector-scoped. Filesystem execution separately enforces identity and node permissions. This explains unauthorized tool visibility; it is not evidence of a file-access bypass.

Showing unusable tools gives an agent misleading capabilities and avoidable authorization failures. A common visibility principle makes the advertised toolset reflect what that caller can actually do. Requiring all operations to be authorized would instead hide useful capabilities from partially authorized callers.

Filesystem grants can authorize a node without access to its ancestors. Administrator membership or root-folder access is therefore not a substitute for filesystem eligibility. Domain permission rules remain authoritative; this decision does not introduce a universal role or new permission grant.

## Alternatives considered

- **Keep filesystem tools visible and reject unauthorized calls:** preserves simpler discovery and protects execution, but continues advertising capabilities the caller cannot use. Rejected for the requested consistent visibility principle.
- **Require administrator membership or root-folder access for filesystem tools:** offers a simple gate, but excludes callers with legitimate direct-node grants and conflates unrelated authority. Rejected.
- **Require permission for every operation in a tool:** avoids advertising any disallowed operation, but hides tools that contain permitted operations. Rejected in favor of at-least-one-operation eligibility.

## Consequences

Discovery must evaluate caller-specific eligibility consistently without leaking another caller's toolset. A visible multi-operation tool can still reject a particular operation or target; that is expected, not a visibility-policy violation.

Eligibility must follow domain authorization rules rather than duplicate a weaker approximation. Tests must distinguish no permitted operations, partial permission, direct-node access, concurrent callers, and revocation followed by a retained-tool invocation.

This decision supplements ADR-008 and the filesystem records; it does not replace their discovery I/O, synchronization, identity, or direct-node authorization boundaries. In particular, it does not authorize per-tool policy scans or discovery-time application-service construction. Discovery projections remain distinct from fresh execution authority, including ADR-008's documented synchronization window.

## Confidence and reevaluation

The principle is explicitly requested; team acceptance and implementation feasibility have not been established. The filesystem eligibility projection and operation-to-permission mappings remain to be specified. Reevaluate through a new ADR if a tool cannot express eligibility faithfully, or synchronization cannot keep discovery sufficiently aligned with permissions. No new consistency guarantee is asserted here.

## Supporting material

- [Administrator discovery authorization](../../api/src/umbod/mcp/administrator/authorization.py) and [filesystem discovery authorization](../../api/src/umbod/mcp/filesystem/authorization.py): investigated visibility checks.
- [ADR-008: Event-Synchronized In-Memory Tool Runtime](ADR-008-event-synchronized-tool-runtime.md): discovery lifetime, caller isolation, and execution authority.
