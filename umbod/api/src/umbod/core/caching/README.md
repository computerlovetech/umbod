# Request-local caching

Backend-independent asynchronous result reuse through explicit, injected cache instances. This module has no database, HTTP, FastAPI, infrastructure, global state, or implicit context dependency. The REST assignable-targets read path opts in through publication and capability-catalogue wrappers; persistence stores, deferred read plans and authoritative mutation/invocation checks remain uncached.

## Module index

- `ports.py`: generic `AsyncRequestCache[KeyT, ValueT]` contract.
- `request_cache.py`: `RequestCache[KeyT, ValueT]` orchestration over an injected key-value driver.
- `models.py`: frozen `CacheStorageKey` with namespace, logical key and generation.
- `errors.py`: `RecursiveCacheLoadError` for recursive same-task loads.
- `__init__.py`: public imports.

## Construction and ownership

`RequestCache` requires a `KeyValueDriver[CacheStorageKey[KeyT], ValueT]` from the [key-value contract](../key_value/README.md). The driver stores successful values only. Pending futures, task ownership, concurrent-load sharing and invalidation policy stay in this module.

Composition creates one cache per request or explicit operation and injects `AsyncRequestCache` into wrapping adapters. The public infrastructure factory `create_request_cache` supplies a fresh in-memory driver; custom composition can inject another driver directly. There is no implicit storage allocation inside the core constructor.

The owner must discard all cache references at the end of the operation. The class does not detect HTTP request boundaries and must not be registered as a singleton. Each cache belongs to one asyncio event loop; thread and cross-loop sharing are unsupported. Shared backend connections do not justify shared request caches.

## Keys and storage scopes

Logical keys must be hashable with stable equality and hashes. Equal keys promise interchangeable loaders and results; the first concurrent caller's loader wins. Distinct operations, result types, owners, tenants, authorization contexts, sessions and transaction snapshots require separate logical keys or cache instances. Database integrations must include complete query semantics, including projection, ordering, limits and cardinality.

Each cache creates a unique UUID namespace; each logical key receives a UUID generation. The driver sees the complete immutable `CacheStorageKey`, not the unqualified logical key. Independent caches remain isolated even when they share a driver. Cache operations never call the driver's global or scope-wide clear operation.

## Contract

`get_or_load(key, loader)` consults the driver and calls the asynchronous, zero-argument loader on a miss. Successful results, including `None`, false values and empty collections, are stored through the driver. Completed futures are not retained as a second value cache: a later call consults the driver again. Prefer immutable results; the in-memory driver returns values by reference, while future remote drivers must define codecs and cannot promise Python object identity.

Concurrent callers for an equal key share the driver lookup, loader, store and resulting success or failure. Different keys do not block one another. This coordination is local to one cache instance, not distributed single-flight across workers.

Loader failures and cancellation are never stored as values. Driver lookup/write failures propagate rather than silently falling back. Failure or initiating-caller cancellation retires the still-current generation so a later call retries with a fresh address, even if the driver committed a write before losing its acknowledgement. Remote adapters must still document ambiguous physical write outcomes. Cancelling a waiting caller does not cancel the shared operation. The initiating caller owns the load: cancelling it cancels its driver/loader operation and current waiters. No background loader tasks are created.

A direct or indirect same-task recursive load of a pending key raises `RecursiveCacheLoadError` instead of deadlocking. Cross-task dependency cycles remain the caller's responsibility.

## Logical invalidation and retention

`invalidate(key)` forgets one generation and detaches its pending slot. `clear()` forgets every generation and pending slot. Both remain synchronous and tolerate missing entries. Subsequent calls use fresh addresses. Existing calls and waiters continue against their captured generation; an old completion, failure or already-started driver write cannot overwrite or evict its replacement.

These operations provide logical invalidation, not physical deletion or guaranteed memory reclamation. Old generation values may remain in the driver until it is discarded or explicitly cleaned up. The default factory's private in-memory driver is discarded with its cache. A long-lived or external driver requires an explicit retention/expiry or namespace-cleanup policy before production integration. The generic driver supports asynchronous deletion and scoped clearing, but request-cache invalidation never performs shared-backend flushing or creates background cleanup work.

There is no TTL, eviction limit, automatic mutation tracking, or security policy in this module. Callers must invalidate after relevant writes or bypass caching when fresh reads are authoritative. Never use cached authorization or credentials as invocation authority.

## Existing boundaries

[ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) records the driver extraction and its limits. [ADR-001](../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) retains database runtime and session ownership in composition. [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) remains unchanged: repeated read-plan executions perform fresh reads. No Redis implementation is included. The [group-permission boundary](../../rest/mcp_permissions/README.md) documents the opt-in assignable-targets wiring.
