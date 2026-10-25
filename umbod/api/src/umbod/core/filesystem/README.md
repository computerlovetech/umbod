# Filesystem

**Module responsibility:** Storage-independent filesystem coordination plus database-neutral namespace and ownership/sharing persistence. Public filesystem operations support root discovery, directory/file creation, node retrieval, child listing, and streamed content reads/writes. Policy storage is independent of these operations.

**Public entrypoint:** Import models, NamespaceDriver, ContentDriver, AccessControlDriver, errors, and Filesystem from `umbod.core.filesystem`. Import FilesystemConfig and composition factories from `umbod.infrastructure`, supplying the existing prepared runtime.database. Core has no infrastructure dependency.

## Files and submodules

- `models.py` defines nodes, metadata, immutable-content references, explicit absence states, principals, ownership, permissions, and access grants. Principal identity includes type, issuer, and provider ID. RootParent, EmptyContent, and UnspecifiedContentType name meaningful absent states without nullable model fields.
- `ports.py` defines namespace, byte-content, and ownership/grant persistence protocols. AccessControlDriver stores policies; it does not resolve identities or evaluate authorization.
- `errors.py` distinguishes namespace failures, OwnershipNotFound, and StorageFailure.
- `namespace.py` supplies shared pure name validation, root/node construction, directory checks, and optimistic content-update rules.
- `stores/` supplies typed per-node/policy tables and database-neutral stores over core.persistence.Database. The [stores index](stores/README.md) describes transactions and identity semantics. Concrete database drivers remain in infrastructure under ADR-001.
- `service.py` coordinates public filesystem operations through injected namespace/content ports. Content storage must complete before revision-checked reference publication. Old or completed unpublished content is not eagerly deleted.
- [Filesystem infrastructure](../../infrastructure/filesystem/README.md) owns configured composition and concrete content adapters under amended ADR-006. Namespace and policy stores share an explicitly supplied Database; content remains independently configurable.

## Ownership and sharing

Ownership assignment is separate, including for the root. Creating a node does not assign an owner. Missing ownership raises OwnershipNotFound; assignment replaces the complete owner without revision checks. Grants are keyed by node UUID and exact principal identity. Re-adding a grant replaces its entire permission set and recursive flag, including empty permission sets. Listing absent grants returns empty; removing an absent grant succeeds.

Policies accept logical UUIDs independently of namespace existence, names, or byte keys. Returned observations are detached from persisted state. This persistence layer neither authenticates callers nor provides default-deny enforcement: authorization evaluation, trusted group resolution, and inherited permissions remain future integration responsibilities.

## Current boundary

Namespace and policy behavior use the same neutral stores against the existing in-memory and SQLite drivers. Content has independent in-memory/local adapters. Test support translates domain language and records public operations; it does not implement a parallel filesystem.

Namespace checks retain exact case-sensitive Unicode-scalar names, sibling collisions, directory-only parents, sorted children, detached metadata, missing-node behavior, and optimistic revisions. Database tests cover reopening, concurrency, transaction failure, schema readiness, and shared application persistence. Local-content tests retain byte publication, symlink, and interrupted-stream/cancellation checks.

The JSON namespace and standalone in-memory namespace are retired. No existing JSON data is read, migrated, or deleted. Metadata replacement, moves, deletion, authorization enforcement, checksums, policy cleanup, and byte garbage collection remain unimplemented. The move-dependent portion of P08 remains deferred; namespace and ownership/grants are still separate operations rather than one combined transaction.

The current scope and verification are recorded in `.atdd/features/filesystem/10-database-namespace-and-policies.md` at the repository root. Earlier feature artifacts preserve implementation history; these tests do not establish all original scenarios or future backend conformance.
