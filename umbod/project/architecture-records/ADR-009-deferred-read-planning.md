# ADR-009: Explicit Deferred Read Planning

- **Status:** Accepted
- **Scope:** Backend-neutral persistence reads, Dashboard catalogue assembly, administration overview and assignable group-permission targets

## Decision

Bounded-context stores may compose validated, typed reads into an explicit request-scoped `ReadPlan`. Registration performs no I/O. Execution freezes registration, applies a separate pure optimization pass, and runs the resulting reads through a supplied `DatabaseSession`.

The first optimization eliminates structurally identical reads, including table/schema descriptors, cardinality, predicates, projection, ordering and limit. Context-owned builders express bulk reads explicitly. Immediate database operations remain available and unchanged.

Handles preserve result types and belong to one plan. Results belong to one execution. Reexecuting a frozen plan performs fresh reads; neither results nor authorization decisions are cached between requests. Failed or cancelled execution returns no partial result object.

## Initial use

Dashboard catalogue assembly plans publication, activation and captured caller-group grants together, using bounded ID batches. Empty inputs generate no reads. Activation predicates include connector kinds to use the existing compound primary key; lookup results retain complete kind-qualified capability identities.

The request reuses loaded downstream definitions, normalized catalogues and connector-invariant readiness results. OpenAPI current-operation reads use successive header and operation plans in one session, restricting operations to the selected connector and exact current catalogue ID.

## Group-permission target reads

The group-permissions page fetches group details and assignable targets separately. Group details already use two scoped grant reads in one session and remain unchanged. Only GET `/api/admin/mcp-permissions/assignable-targets` opts into planned availability state; permission mutations and invocation retain their existing authoritative dependencies.

The GET prepares native, OpenAPI and downstream catalogues before registering state reads. The same request-owned catalogue wrappers serve subsequent enumeration and resolution. A single downstream definition listing is shared with catalogue loading and personal connector decoration. Publication requirements include eligible personal connector definitions even when they have no canonical capabilities; activation requirements include only connector IDs represented by enumerated capabilities. The existing bounded query builders deduplicate and sort each scope independently, reading at most 200 connector IDs per batch. Empty requirements open no state session.

After preparation, publication and activation reads execute together through one supplied session. Resolved readers perform no further database I/O and fail closed for absent facts. Activation lookups retain complete connector-kind, connector-ID, capability-kind and key identities. The bulk query selects all capability statuses and connector kinds for the scoped IDs, not exact individual capability keys. Catalogue preparation and native configuration readiness remain outside the planned-state transaction; this is not a fully atomic endpoint snapshot.

For the existing single-shared-downstream fixture, one, forty and one hundred enabled tools now require five reads and four sessions on both backends, rather than the cached path's N+5 reads and sessions. The five reads are connector inventory, downstream definitions, one downstream catalogue, publication and activation. Catalogue reads still grow with connector count, and native configuration readiness is unchanged. No universal endpoint budget or production latency guarantee is implied.

## Administration overview

GET `/api/admin/overview` uses request-scoped read planning for a metadata summary, rather than invoking connector-management endpoints. Inventory and scoped dependent reads share a supplied session. Counts use registered native tools, current OpenAPI operation identities and shared downstream snapshots; stale activations and personal inventories do not contribute.

Configuration counts mean persisted current-configuration presence, not successful credential decryption or live service readiness. The overview must not load secrets or invocation policies, perform network discovery, or normalize complete capability schemas merely to count them. Narrow context-owned projections and bounded ID batches avoid per-tool reads. Downstream snapshots currently embed tool metadata, so reading those snapshots remains necessary; this is not a claim of database-side aggregate counts or constant work for arbitrary connector inventories.

A failed database read aborts the summary snapshot; the frontend reports unavailable counts rather than zeros. This intentionally replaces independent HTTP-source failure isolation with one coherent read. Results are not cached across requests or used as execution authority.

## Consistency and authority

The caller and membership are captured before asynchronous catalogue loading. Planned state reads share one transaction. This is not a claim that all Dashboard data, configuration, descriptions and personal authorization reads share one atomic snapshot. SQLite and in-memory session guarantees remain defined by their existing adapters.

No ordinary session-opening store is invoked inside plan execution. Transactions do not include network discovery, OAuth operations or response rendering. Existing personal admission and mutation transactions remain fresh and authoritative. Request-local readiness reuse never becomes invocation authority or shared credential storage.

This extends [ADR-001](ADR-001-backend-neutral-persistence.md) without changing runtime ownership. It does not replace the event-synchronized MCP discovery boundary in [ADR-008](ADR-008-event-synchronized-tool-runtime.md).

## Alternatives and limits

Implicit query interception and global caches were rejected because they hide execution and authorization lifetimes. Full-table snapshots were rejected in favor of scoped bulk requirements. A general cost-based optimizer, arbitrary query merging, joins, write planning and cross-HTTP-request composition are deferred.

The separate planning/optimization/execution stages leave room for safe rewrite rules, narrower projections and backend-specific execution strategies. Future rules must preserve ordering, limits, cardinality, decoding errors and owner isolation, with behavioral and query-budget regressions.

## Consequences

The current shared-downstream catalogue regression performs the same nine database reads and six sessions for one and forty tools, on both in-memory and SQLite backends, without writes. This is a bounded fixture result, not a universal latency or query-count guarantee. Broader batching across connectors remains future work.
