# Infrastructure

**Module responsibility:** Low-level persistence drivers and persistence runtime composition, as defined by ADR-001. Domain-specific modules and policy belong in core.

**Read when working with:** Backend selection, database drivers, connection handling, schema preparation or persistence runtime assembly.

## Submodules

### `persistence/`

**Public entry:** `ConfiguredPersistenceRuntimeProvider` (also re-exported from `umbod.infrastructure`). Backend selection happens once through that provider; callers receive a neutral `PersistenceRuntime` with a `Database` port.

**Internal:** `inmemory/` and `sqlite/` hold driver implementations, compilers, readiness, and schema preparation. Do not import those packages from application modules or from non-adapter tests.
