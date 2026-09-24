# Infrastructure

**Module responsibility:** Adapters that implement core ports using external systems and runtime-specific technology.

**Read when working with:** External I/O, storage implementations, or dependency assembly that connects adapters to the core.

## Submodules

### `persistence/`

**Public entry:** `ConfiguredPersistenceRuntimeProvider` (also re-exported from `umbod.infrastructure`). Backend selection happens once through that provider; callers receive a neutral `PersistenceRuntime` with a `Database` port.

**Internal:** `inmemory/` and `sqlite/` hold driver implementations, compilers, readiness, and schema preparation. Do not import those packages from application modules or from non-adapter tests.
