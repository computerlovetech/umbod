# Filesystem database-neutral stores

**Module responsibility:** Implement NamespaceDriver and AccessControlDriver over the existing Database port without choosing a database backend. Follow ADR-001's bounded-context store pattern. Constructors only retain dependencies; application persistence readiness prepares the tables.

## Files

- `schema.py` declares filesystem_nodes, filesystem_ownership, and filesystem_grants with typed row/key codecs. Node identity, parent, name, and revision are separately queryable; each validated payload describes one node, not a whole namespace snapshot. Record validation keeps scalar indexes consistent with payload identity and namespace invariants. Ownership keys use node UUID; grant keys include node UUID and all principal identity components.
- `namespace.py` implements DatabaseNamespace. Root provisioning is idempotent within a serialized transaction. Once initialized, reads use a read transaction without acquiring SQLite's shared database writer lock; a missing root closes the read session before retrying initialization and the operation in a serialized-write session. Creation validates parent/name/collision before insertion; content-reference updates check kind/revision before publication. Detached node observations preserve stored values. Children sort by Unicode code-point order.
- `access_control.py` implements DatabaseAccessControl. Owner/grant writes replace complete records in serialized transactions. Missing owner raises OwnershipNotFound; missing grant listings/removals are safe. Policy operations use logical UUIDs without namespace lookup or authorization evaluation.
- `session.py` maps storage failures into StorageFailure while preserving domain errors and cancellation. Database sessions retain responsibility for commit and rollback.
- `__init__.py` exposes the neutral store implementations within this bounded context. Normal application composition uses the root infrastructure factories.

## Transaction and lifecycle boundary

All namespace mutation checks and publication share one serialized-write session. Root initialization uses the fixed root UUID and never overwrites an existing root. Stores over the same prepared Database observe the same namespace and policies; SQLite runtimes targeting the same persistent database retain them across reopening and serialize concurrent writers.

Ownership remains independent of node creation; there is no implicit owner, combined node-owner transaction, foreign-key namespace existence requirement, or authorization decision. Principal type, issuer, and provider ID are exact identity components; grants for different tuples or different node UUIDs do not overlap. Empty permission sets and recursive flags are stored, not interpreted.

The application runtime owns schema readiness and database shutdown. Filesystem tables join its normal readiness registry. Stores do not create runtimes, issue SQLite SQL, import infrastructure, or depend on host filesystem modules.

Database transactions exclude byte storage. Filesystem stores preserve optimistic publication after successful content storage; cleanup of unreferenced bytes or policies remains deferred. JSON namespace import/migration is not part of these stores.
