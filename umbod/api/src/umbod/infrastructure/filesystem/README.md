# Filesystem adapters

**Module responsibility:** Infrastructure implementations of the core namespace/content ports and their configured composition, as defined by ADR-006. Import configuration and factory functions from `umbod.infrastructure`; concrete classes stay internal to these driver modules. Core service and domain rules do not import infrastructure.

## Configured composition

A caller supplies FilesystemConfig to create_filesystem, and the factory constructs the declared namespace/content adapters and the final service. Adapter choices are independent: each selects inmemory or local, with an explicit directory for local storage. No default adapter, global state, environment loading, or REST/MCP wiring is hidden in composition.

Each factory call creates new adapter instances. Retain the result for the intended standalone storage lifetime; repeated calls do not share in-memory data. Repeated local configurations reopen the same persisted directories. Mixed backends are allowed, but persistent namespace plus ephemeral content cannot preserve readable bytes across restarts, and ephemeral namespace plus persistent content loses its logical hierarchy.

For a future request-scoped host, create_namespace_driver and create_content_driver allow long-lived infrastructure adapters to be composed separately and injected into request-scoped services. Do not construct fresh in-memory adapters for every request or put application services on app.state.

## Files

- `config.py` defines explicit namespace/content backend declarations with required local directories and no backend defaults.
- `factory.py` selects namespace/content adapters from typed configuration and returns the composed Filesystem. Unsupported declarations fail validation; dispatch has no fallback. Concrete drivers are imported lazily only when selected, so importing composition does not load POSIX filesystem implementations.
- `inmemory.py` provides InMemoryNamespace and InMemoryContent. Namespace mutations are serialized and content objects are published only after their streams complete. Reuse the same instances to share in-memory state across service instances.
- `local_namespace.py` provides LocalNamespace. Its configured directory contains a validated, versioned `namespace.json` snapshot and a stable `namespace.lock` file. Every operation reloads the snapshot under an interprocess lock; mutations flush a temporary snapshot, atomically replace the current snapshot, and sync the directory. Corrupt snapshots fail instead of silently resetting the filesystem.
- `local_content.py` provides LocalContent. Its configured directory stores immutable content objects under generated opaque UUID keys. Byte streams are written in bounded chunks to temporary files and published with non-overwriting links only after completion and fsync. Logical node names never become host filesystem paths.
- `objects.py` centralizes directory preparation, content-key validation, regular-file checks, and directory synchronization.
- `io.py` offloads file operations and drains in-flight work before returning cancellation, preventing descriptor-close races and namespace commits occurring after cancellation has already been returned.

## Guarantees and limits

The namespace adapter provisions one shared root. Independent local adapter instances and processes targeting the same namespace directory share that root and serialize updates. Namespace creation and content-reference publication use the same core rules as the in-memory adapter. Returned node metadata is detached from persisted state.

Local adapters require POSIX filesystems supporting flock, atomic rename, hard links, and fsync. Use dedicated trusted directories; hostile concurrent modification of directory ancestors is not contained. Existing directory and object symlinks are rejected. Network filesystem semantics are not established by this implementation.

The local namespace rewrites and validates the entire snapshot per mutation; this favors a small standalone filesystem rather than large namespaces. Local data survives reopening; in-memory data survives only while its adapter instances are retained.

Cancellation is not a transaction rollback: a namespace operation already dispatched can commit, but its worker is drained before cancellation returns. Re-read state before retrying an operation with an uncertain outcome. Interrupted streams and cancellation clean incomplete content temporaries. Process crashes may leave private temporary files. Old and completed unpublished content objects are deliberately retained for future concurrency-safe cleanup.

There is no application wiring, policy backend, authorization enforcement, recursive deletion, move operation, metadata replacement operation, or garbage collector in these adapters.
