# Groups

Shared catalogue of exact group claim values. Registration grants no connector or filesystem access and does not infer issuers or manage identity-provider groups. New registrations reject blank-only IDs without trimming nonblank values; historical identities remain unchanged.

- `models.py` defines catalogue projections, validated registration requests and in-use deletion failure.
- `ports.py` defines the catalogue transaction and usage contracts.
- `service.py` performs registration and atomic usage-checked deletion through those ports.
- `in_memory.py` provides the transactional in-memory catalogue adapter.
- `stores/schema.py` owns the existing `mcp_permission_groups` table, record, key and projections. Permission schema exports remain aliases of these same objects.
- `stores/registration.py` registers IDs inside a caller-owned database transaction.
- `stores/service.py` implements catalogue reads and serialized write transactions over the shared Database.
- `stores/composition.py` combines connector and filesystem usage adapters in the same transaction. Business services do not import either domain schema.

Readiness reconciliation lives in `infrastructure/persistence/group_reconciliation.py`, not reads. It adds registrations from existing connector/capability permissions, all filesystem GROUP grants and GROUP ownership without modifying policies. Grant removal never removes registrations. Deletion refuses any remaining reference, including orphan-node and empty-permission grants, and never cascades.
