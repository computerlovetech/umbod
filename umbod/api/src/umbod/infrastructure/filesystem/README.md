# Filesystem composition and content adapters

**Module responsibility:** Compose database-neutral filesystem stores with independently selected concrete content storage, as defined by ADR-006. Import configuration and factory functions from `umbod.infrastructure`; concrete content classes remain internal. Core never imports infrastructure.

## Configured composition

A caller supplies FilesystemConfig and an explicit Database to create_filesystem. Configuration selects content storage only: inmemory or local, with a required directory for local bytes. Namespace and ownership/grant persistence use the existing application's database driver; no filesystem-specific database backend selection or private runtime is created.

create_namespace_driver and create_access_control_driver construct neutral stores over the supplied Database. create_content_driver constructs the selected content adapter separately. Ownership remains an independent operation; constructing or using Filesystem does not assign an owner or enforce permissions.

The persistence runtime owns database readiness and shutdown. Filesystem tables participate in the existing application schema registry. Factories and constructors do not prepare schemas. Inject the same prepared runtime.database into stores that must share state. Fresh store objects over that database see the same nodes and policies.

Each content factory invocation creates a new adapter. Retain in-memory content for its intended storage lifetime; fresh instances do not retain previous bytes. Matching local content directories reopen stored objects. Persistent namespace with ephemeral content cannot preserve readable bytes across process restarts.

Future request-scoped hosts should inject shared infrastructure dependencies into operation services, not create private database runtimes or fresh in-memory content per request. Do not put application services on app.state.

## Files

- `config.py` defines validated content backend declarations and FilesystemConfig, with no content default. Retired namespace selectors are rejected.
- `factory.py` composes the service and namespace/access-control stores from an injected Database and selects content storage. Concrete content drivers are loaded lazily.
- `inmemory.py` provides InMemoryContent. Objects become visible only after their streams complete.
- `local_content.py` provides LocalContent. It writes bounded stream chunks to temporary files and publishes immutable objects under opaque UUID keys with non-overwriting links after completion and fsync. Logical node names never become host paths.
- `objects.py` centralizes trusted-directory preparation, content-key validation, regular-file checks, and directory synchronization.
- `io.py` offloads host file operations and drains in-flight work before returning cancellation to prevent descriptor-close races.
- The [core stores index](../../core/filesystem/stores/README.md) describes namespace/policy schema and database-neutral behavior.

## Guarantees and limits

Local byte storage requires POSIX filesystem support for hard links, file descriptors, and fsync. Use dedicated trusted directories; hostile concurrent modification of directory ancestors is not contained. Existing directory/object symlinks are rejected. Network filesystem semantics are not established.

Interrupted streams and cancellation clean incomplete content temporaries. Process crashes may leave private temporaries. Old and completed unpublished objects remain available for future concurrency-safe cleanup. Database transactions do not encompass byte publication: store bytes first, then publish their namespace reference with the expected revision. Re-read state before retrying operations whose commit outcome is uncertain.

The JSON namespace adapter and its directory/lock/snapshot configuration are removed. Existing JSON files are not read, migrated, or deleted. This is a deliberate configuration change; callers must provide a prepared Database.

There are no filesystem REST/MCP entrypoints, authorization enforcement, identity/group resolution, inherited-permission evaluation, new namespace operations, or garbage collection here.
