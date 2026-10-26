# Authorized filesystem creation

- `ports.py` defines FilesystemCreation.create_file and create_directory using CallerSnapshot, parent ID, name and metadata only.
- `service.py` supplies CreationService with an identity resolver and FilesystemTransactions.
- `__init__.py` exports the port and service.

Resolve exactly once before opening a transaction. Unresolved identity denies without any writes. Within one serialized-write session the shared authorization evaluator checks parent DISCOVER first, WRITE second, then creates the node and assigns the resolved USER as owner. Parent revocation and creation serialize; there is no check/use gap across transactions. Failures and cancellation roll back node and owner together.

No caller-supplied owner or grants are accepted. Group parent grants can authorize creation, but groups never become the child owner. No grants are created or inherited. Before assigning ownership, creation rejects any ownership or grants already stored for the newly returned UUID with StorageFailure, rolling back the node without deleting or overwriting legacy orphan policies. Raw policy stores still accept orphan UUIDs. The creator receives every child permission through ownership; other users and group peers receive none without explicit child policy. Missing or unowned parents deny; an authorized file parent raises WrongNodeKind. Existing name/collision errors are preserved.

The shared browsing summary projection returns detached metadata and no content references. Raw Filesystem/NamespaceDriver APIs remain trusted unenforced capabilities with independent ownership. REST and MCP adapters capture authenticated snapshots and delegate empty creation to this port. They do not select owners, generate grants, or reproduce creation authorization.
