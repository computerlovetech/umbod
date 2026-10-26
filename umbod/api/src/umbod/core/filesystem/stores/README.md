# Filesystem database-neutral stores

**Module responsibility:** Implement NamespaceDriver and AccessControlDriver over the existing Database port without choosing a database backend. Follow ADR-001's bounded-context store pattern. Constructors only retain dependencies; application persistence readiness prepares the tables.

## Files

- `schema.py` declares filesystem_nodes, filesystem_ownership, and filesystem_grants with typed row/key codecs. Node identity, parent, name, and revision are separately queryable; each validated payload describes one node, not a whole namespace snapshot. Record validation keeps scalar indexes consistent with payload identity and namespace invariants. Ownership keys use node UUID; grant keys include node UUID and all principal identity components.
- `namespace.py` implements DatabaseNamespace and reusable session-bound SessionNamespace operations. Raw lazy unowned root initialization is idempotent within a serialized transaction. Once initialized, reads use a read transaction without acquiring SQLite's shared database writer lock; a missing root closes the read session before retrying initialization and the operation in a serialized-write session. Creation validates parent/name/collision before insertion; content-reference updates check kind/revision before publication. Detached node observations preserve stored values. Children sort by Unicode code-point order.
- `access_control.py` implements DatabaseAccessControl and reusable session-bound SessionAccessControl operations. Owner/grant writes replace complete records in serialized transactions and register exact GROUP IDs in the shared catalogue in that same session; USER and SYSTEM writes do not register IDs. Missing owner raises OwnershipNotFound; missing grant listings/removals are safe. Policy operations use logical UUIDs without namespace lookup or authorization evaluation.
- `group_usage.py` checks every node's GROUP grants, regardless of recursive flag, permissions or namespace presence, and GROUP ownership for shared catalogue deletion. Issuer-qualified policy identity is unchanged.
- `administration.py` implements narrow root administration sessions and read/write transactions. Root-scoped queries never initialize on inspection; child existence uses a key-only projection. Serialized writes initialize only after core revision and scope validation. Unrelated orphan policies are untouched.
- `transactions.py` implements FilesystemTransactions with exactly one SERIALIZED_WRITE Database session shared by session-bound namespace and policy drivers. It reuses root initialization without nesting transaction-opening wrappers, including on the in-memory driver.
- `session.py` maps storage failures into StorageFailure while preserving domain errors (including PermissionDenied and ProvisioningConflict) and cancellation. Database sessions retain responsibility for commit and rollback.
- `__init__.py` exposes the neutral store implementations within this bounded context. Normal application composition uses the root infrastructure factories.

## Transaction and lifecycle boundary

All namespace mutation checks and publication share one serialized-write session. Root initialization uses the fixed root UUID and never overwrites an existing root. Stores over the same prepared Database observe the same namespace and policies; SQLite runtimes targeting the same persistent database retain them across reopening and serialize concurrent writers.

Raw APIs retain independent ownership with no implicit owner, foreign-key namespace existence requirement, or authorization decision. The opt-in creation service uses the combined transaction port for atomic parent authorization, node creation and owner assignment. Trusted root provisioning uses it for atomic system ownership and initial direct grants. Principal type, issuer, and provider ID are exact identity components; grants for different tuples or different node UUIDs do not overlap. Empty permission sets and recursive flags are stored, not interpreted.

The application runtime owns schema readiness and database shutdown. Filesystem tables join its normal readiness registry. Stores do not create runtimes, issue SQLite SQL, import infrastructure, or depend on host filesystem modules.

Database transactions exclude byte storage. Filesystem stores preserve optimistic publication after successful content storage; cleanup of unreferenced bytes or policies remains deferred. JSON namespace import/migration is not part of these stores.
