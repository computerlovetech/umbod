# ADR-010: Key-Value Storage Drivers Below Request Cache Policy

- **Status:** Accepted
- **Scope:** Generic key-value storage, request-cache composition and opt-in assignable-target reader wrappers

## Decision

Define the asynchronous generic `KeyValueDriver` protocol and explicit `KeyValueHit` / `KeyValueMiss` results in `umbod/core/key_value/`. Drivers provide get, set, delete and scoped clear operations. Missing values remain distinct from stored `None`, false values and empty collections.

Concrete drivers belong in `umbod/infrastructure/key_value/`. Initially only an in-memory driver exists. Public infrastructure factories construct fresh drivers and operation-owned request caches; concrete implementations are not root exports. Core never imports infrastructure or chooses a backend implicitly.

`RequestCache` remains in `umbod/core/caching/` and requires an injected key-value driver. It owns request-cache policy: local pending-load coordination, task ownership, recursion detection, cancellation and logical invalidation. The driver stores successful values only, never futures, tasks, loaders or exception states. Completed cache calls consult the driver again rather than retaining a second result cache in core.

Wrapping adapters depend on the core cache protocol, not concrete storage. The initial driver extraction left production readers untouched; the assignable-target integration below opts in explicitly.

## Scope and invalidation

Each cache instance creates a unique UUID namespace and maps each logical key to a UUID generation. The storage address includes namespace, logical key and generation. Equal logical keys in separate cache instances cannot share results, including when the driver is shared.

Pending coordination is installed before any driver lookup. Invalidating a key synchronously discards its generation and pending slot; clearing discards all generations and pending slots. Subsequent reads use fresh addresses. Existing callers and waiters retain their old load outcome. Captured generation addresses prevent an already-started asynchronous write from repopulating a replacement entry. Failure or cancellation retires the generation only while the failing load still owns that key, preventing unacknowledged committed writes from being reused without disturbing a newer generation.

Invalidation is logical, not physical erasure. Obsolete generations can remain in storage until the owning driver is discarded or an explicit retention/cleanup policy removes them. The default factory supplies a private in-memory driver discarded with the cache. A long-lived external backend requires deliberate expiry or namespace cleanup before integration. Cache clearing must never flush a shared server or unrelated namespaces.

## Lifetimes and future drivers

Composition owns one cache per request or explicit operation. A shared connection pool is not a shared request cache. Local concurrent-load sharing is not distributed locking; it coordinates only callers sharing that cache instance.

A future Redis adapter must define typed key/value codecs, validation of external bytes, scoped key ownership, expiry/cleanup, connection lifetime and failure semantics. Arbitrary hashable Python keys and values are supported by the in-memory adapter; portable encodings and Python object identity are not promised for remote storage. Raw pickle loading is not an implicit part of this boundary. Driver exceptions propagate; a remote write timeout may have an ambiguous completion outcome and must be documented by the adapter.

TTL, Redis configuration, Redis clients, distributed single-flight, cross-request result reuse, persistence integration and delivery wiring beyond the assignable-target GET path are deferred. No new backend selector is added to database runtime configuration.

## First reader integration

GET `/api/admin/mcp-permissions/assignable-targets` creates request-owned publication and capability-catalogue wrappers through its own dependency chain. Publication results are shared by operation and connector ID, including false values. OpenAPI and downstream catalogues are listed once, copied and indexed by complete capability identity, then reused for readiness resolution. Returned nested schemas cannot mutate the retained snapshot. Native catalogues retain their existing in-memory indexes; activation and native configuration readiness are unchanged.

This intentionally captures read-model facts for the current request without claiming an atomic database snapshot. No cross-request values, credentials or grants are retained. Permission mutations, other group reads and invocation continue through their existing uncached dependencies. Subsequent requests observe committed state changes. A per-identity memoizer alone was rejected because list-to-resolve catalogue duplication was the measured bottleneck.

The single-shared-connector query-budget fixture falls from 4N+4 reads/sessions to N+5 for N enabled tools on both persistence backends. Unique activation reads remain linear and batching is deferred. This is a scoped regression, not a universal budget or production latency guarantee.

## Relationship to accepted decisions

This extends the infrastructure placement boundary in [ADR-001](ADR-001-backend-neutral-persistence.md) for a separate generic storage concern without changing database ownership, schemas or migrations. [ADR-009](ADR-009-deferred-read-planning.md) is unchanged: repeated read-plan executions perform fresh reads. Request-local reuse must not become authoritative authorization or shared credential storage.

## Verification

Public cache contracts retain successful-value reuse, concurrent-load sharing, failure retries, cancellation, recursion detection and invalidation behavior. Driver contracts cover explicit misses, stored false values, compound keys, overwrite/delete/clear and instance isolation. Suspended-driver tests verify generation isolation when lookup or write I/O overlaps invalidation, and namespace isolation when caches share a driver. Architecture checks preserve inward dependencies and composition-only infrastructure exports.
