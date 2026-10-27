# Infrastructure

**Module responsibility:** Low-level persistence, filesystem and key-value storage drivers with their composition boundaries, as defined by ADR-001 and its scoped ADR-006 and ADR-010 extensions. Domain-specific models, ports, rules, and services belong in core.

**Read when working with:** Backend selection, database or filesystem storage drivers, connection handling, schema preparation, or configured storage/service composition.

## Submodules

### `key_value/`

**Public entry:** Import `create_inmemory_key_value_driver` or `create_request_cache` from `umbod.infrastructure`. Both create fresh operation-owned objects. Custom cache composition injects a core `KeyValueDriver` into `RequestCache`; connections to any future remote backend must not extend the cache's request lifetime.

**Internal:** The concrete in-memory driver stores successful key-value data, not asyncio futures or caching policy. The [local index](key_value/README.md) describes the generic storage operations. Redis, serialization, expiry and distributed coordination are not implemented. Cache logical invalidation does not physically delete backend entries; external-driver retention must be explicitly designed before integration. [ADR-010](../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) records this boundary.

### `persistence/`

**Public entry:** `ConfiguredPersistenceRuntimeProvider` (also re-exported from `umbod.infrastructure`). Backend selection happens once through that provider; callers receive a neutral `PersistenceRuntime` with a `Database` port.

**Internal:** `schema_preparation.py` prepares the shared catalogue table once and runs idempotent `group_reconciliation.py` before readiness completes, registering existing connector/capability groups and all filesystem GROUP grants/ownership without changing grants or normalizing identities. `inmemory/` and `sqlite/` hold driver implementations, compilers, readiness, and schema preparation. Do not import those packages from application modules or from non-adapter tests.

### `filesystem/`

**Public entry:** Import FilesystemConfig, its content variants, and create_filesystem from `umbod.infrastructure`. Supply the existing prepared runtime.database explicitly. Separate create_namespace_driver, create_access_control_driver, and create_content_driver functions support explicit dependency lifetimes and service injection. Namespace and ownership/grants use the existing persistence drivers, not another filesystem-specific database selector.

**Internal:** Concrete in-memory/local content drivers, content configuration, composition factories, and host-filesystem I/O helpers live here. The [local index](filesystem/README.md) describes persistence and platform assumptions. Concrete driver classes are not root exports; only driver-specific tests under `tests/umbod/infrastructure/filesystem/` may deep-import them. Backend-neutral filesystem models, ports, rules, service, and database-neutral stores/schema remain in core. The shared persistence readiness registry includes filesystem tables. JSON namespace storage is retired without implicit migration.
