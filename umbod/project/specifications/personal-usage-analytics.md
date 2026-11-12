---
type: Feature Specification
title: Personal MCP usage analytics
description: User-owned Dashboard counts collected from MCP completion signals through bounded asynchronous application-persistence writes.
---

# Scope

Authenticated Dashboard users see their own observed MCP usage alongside the connector catalogue. The first slice provides totals and daily counts by tool, resource, and prompt, split into success, failure, and cancellation. The window is seven UTC calendar days by default, or thirty days, including today. All dates are present, including zero-usage dates.

Counts describe observed completions, not exhaustive wire requests. Built-in and connector tool executions count. Resource reads, including instantiated templates, and prompt retrievals count. Discovery lists, inventory observations, gateway/code-mode orchestration wrappers, approval continuations, and requests rejected before completion observation do not count. Nested connector executions count individually. Existing tool lifecycles do not emit cancellation completions; no missing observations are invented.

This feature is informational, eventually consistent, and best effort. It is not billing-grade accounting. Pending observations can be lost on process failure. There is no historical backfill or per-name ranking in this slice.

# Collection and storage

Existing application-local signals retain their domain contracts. Dedicated named receivers capture trusted usage ownership, project allowlisted OpenTelemetry Logs records, and enqueue synchronously without database or network I/O. Logging receivers remain independent. Collection does not parse stdout, call the public OTLP ingestion endpoint, or change acknowledged telemetry export behavior.

Ownership is a versioned opaque hash of exact verified issuer and subject. Email, display name, session, client-supplied owner, and diagnostic actor ID are not ownership authorities. Explicit local simulation uses the reserved local issuer; unavailable or untrusted identity is excluded. The same resolver is used by MCP collection and REST reads. Raw claims never enter usage records. For verified Google tokeninfo results that omit issuer, the MCP adapter uses the configured REST issuer only when it is an approved Google issuer; it never supplements unknown providers or overwrites a declared issuer.

Queued immutable records contain a stable event ID, trusted opaque owner, completion timestamp, operation category, outcome, nonnegative duration, valid correlation when available, and a canonical OTLP Logs representation. Arguments, bodies, credentials, raw resource URIs, prompt names, arbitrary metadata, and exception stacks are excluded. No per-user Prometheus labels are added.

One worker per MCP application writes batches through the existing application PersistenceRuntime database. A deduplication/event table retains the safe OTEL records. Daily owner/category/outcome rollups are incremented only for newly inserted event IDs in the same serialized transaction. Replaying an ambiguously committed batch cannot double count. REST and MCP processes share the configured persistent application database; independent in-memory processes do not share observations. The separate telemetry analytics SQLite database remains unchanged. Usage transactions acquire the writer slot without waiting; contention follows the worker retry policy instead of delaying primary application writes.

# Operational defaults

Collection is enabled by default and can be disabled. Validated configuration supplies queue capacity 4096, maximum record size 2048 bytes, batch size 128, flush deadline one second, persistence attempt timeout five seconds, three retries after the initial attempt with delays 250 milliseconds, one second, and four seconds, shutdown deadline ten seconds, and retention ninety UTC days. Bounds prevent unbounded configuration values.

The queue drops the newest record when full. One in-flight batch is retained across retries; there is no secondary retry queue or task per record. Projection failures, oversized records, overflow, exhausted retries, and shutdown losses have bounded aggregate counters and sanitized, rate-limited application-failure notifications. Anonymous/untrusted observations are excluded without per-call diagnostic noise.

Shutdown stops admission, drains within its deadline, and terminates the worker before database shutdown. Remaining work is accounted for as dropped. The shutdown budget reserves cancellation/cleanup time. Supported SQLite VM operations are interrupted and rolled back before connections are released; blocked OS I/O or uncooperative extension callbacks are not a hard real-time guarantee. Cleanup is never abandoned, and a budget overrun is reported after safe worker termination. Retention removes expired event and rollup rows using indexed date fields. Disabled collection does not activate receivers or a worker, and personal queries return unavailable rather than fabricated zero counts.

# Personal API

GET /api/me/usage accepts only days=7 or days=30. Days defaults to seven at the HTTP boundary. Ownership is derived exclusively from authenticated request context. Owner, user, and scope parameters are not accepted. Ordinary authenticated users do not require administrator privileges.

The response contains identity_key for the existing Dashboard identity fence, range with start-inclusive/end-exclusive ISO dates and timezone UTC, as_of UTC timestamp, totals, and daily rows. Counts contain tool, resource, and prompt groups; each group contains nonnegative success, failure, and cancelled counts. Totals equal the daily sum from one read snapshot. The identity fence is not the storage ownership key. Responses use Cache-Control: no-store. Invalid query input is rejected, unresolved ownership is forbidden, and unavailable storage/collection is distinct from a successful empty result.

# Dashboard

Your usage is a feature-owned section above Connectors, with total operation counts, category counts, outcome counts, an accessible daily trend/table, seven/thirty-day selection, and refresh/retry. Existing shared controls, feedback, and theme tokens are reused; the administrator analytics workflow is not reused.

Usage state is separate from catalogue and administrator-access state. Catalogue loading or failure cannot hide usage, and usage failure cannot block catalogue interaction. Loading, empty, unavailable, and failed states are distinct. All mutable and derived state belongs to a dedicated state class. Abort, revision, range, and identity fences prevent obsolete responses from replacing current data. Identity changes, authentication loss, disposal, and focus revalidation clear identity-bound snapshots before they can be reused.

# Acceptance

- Given two authenticated users, when either reads Dashboard usage, only their own persisted counts are returned; equal subjects at different issuers remain isolated.
- Given eligible tool, resource, and prompt completion signals, when the worker commits a batch, their exact category/outcome counts become visible through the personal endpoint and Dashboard.
- Given wrapper and discovery completions, when they are observed, they contribute no usage; nested eligible executions still contribute individually.
- Given slow or failed persistence, when an invocation completes, its result and other signal receivers remain unchanged and the request does not await analytics persistence.
- Given duplicate event IDs or an ambiguous commit, when the same batch is retried, event storage and rollups count each event once.
- Given a UTC boundary and a seven/thirty-day query, when counts are read, completion time determines the correct day, all dates are zero-filled, and totals equal daily sums.
- Given overflow, repeated writer failure, or shutdown timeout, when records are dropped, loss is bounded and observable without leaking user identities or invocation data.
- Given pending records at graceful shutdown, when the deadline permits writes, the records are committed before persistence shuts down; an unavailable writer cannot block shutdown indefinitely.
- Given persisted records, when processes restart against the same application database, personal counts remain available. Expired records and rollups are removed according to retention.
- Given stale responses, changing periods, account changes, authentication loss, or disposal, when pending requests settle, no previous identity or obsolete range becomes visible.
- Given usage loading/error/empty states, when the catalogue loads independently, both sections retain their own controls and recovery behavior.

# Verification

Domain, queue, ownership, and state tests use injected clocks and I/O ports. Persistence adapter contracts cover in-memory behavior and SQLite durability, indexes, atomic rollups, and replay. In-process application tests verify real composition, receiver isolation, normal-user authorization, and canonical OTEL serialization. Disposable Kind tests verify authenticated MCP-to-REST visibility across processes and user isolation. Frontend tests, static checks, shared Semgrep, module/index checks, and browser verification at http://localhost:3010 are required before completion.
