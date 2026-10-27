# Downstream discovery runtime

Implements the shared downstream read model required by [ADR-008](../../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md).

- `ports.py`: explicit snapshot-loader and runtime contracts.
- `models.py`: stable discovery snapshots and unavailable-runtime errors. Snapshots contain structural shared metadata, publication/activation/readiness projections, descriptions and namespace indexes, never decrypted credentials or caller authorization decisions.
- `loader.py`: background persistence loading and normalization; reads each shared catalog once per rebuild and retains only credential availability facts. Personal definitions contribute namespace reservations, not private inventories.
- `catalog.py`: application-owned in-memory adapter. Rebuilds are serialized independently of readers and publish by one snapshot replacement. Failed rebuilding closes discovery until a successful retry; cancellation preserves the previous complete snapshot.
- `definitions.py`: list-only definition projection for personal connector enumeration without a shared-definition database scan. Owner availability and execution admission remain authoritative and operation-scoped.
- `__init__.py`: explicit factory and public contracts. Construction does not perform I/O; the application must reconcile before discovery readiness.

`provider.py` captures the runtime snapshot and caller membership before asynchronous listing, then evaluates current grants against that captured caller. Retained shared tools and personal execution continue to check current authority. The background-only `native_capability_projection` entrypoint reconciles before publishing inventory and comparing prompt/resource projections. Durable messaging and startup replay are composed by the MCP application; ordinary discovery never loads missing state on demand.
