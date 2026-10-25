# Virtual filesystem

**Module responsibility:** Standalone storage-independent filesystem coordination. This initial slice supports discovery of a driver-provided shared root, directory/file creation, node retrieval, child listing, and streaming content reads/writes.

**Public entrypoint:** Import models, ports, configuration, and `VirtualFilesystem` from `umbod.core.virtual_filesystem`. Import `create_virtual_filesystem` from `umbod.core.virtual_filesystem.adapters` for configured production composition.

## Files

- `models.py` defines Pydantic node, metadata, immutable-content reference, and node-kind boundary values. Fields are explicit; RootParent, EmptyContent, and UnspecifiedContentType model absence as named states rather than nullable values. These states replace the original design's None representations.
- `config.py` defines frozen, validated configuration with independent namespace/content adapter selections. Each declares its type explicitly; local variants require a directory and in-memory variants reject one. Configuration can be supplied by a caller's main without depending on global application settings or environment loading.
- `ports.py` defines namespace and content dependency protocols and the byte-stream type. The namespace publication operation replaces a complete content reference with an expected revision; general metadata patches and content clearing are not part of this initial port surface.
- `errors.py` defines distinguishable namespace and storage failures.
- `namespace.py` owns validated snapshot state and shared namespace rules for hierarchy, names, detached observations, and optimistic content publication.
- `adapters/` supplies production in-memory and POSIX local-filesystem namespace/content adapters. The [adapter index](adapters/README.md) describes persistence, concurrency, platform assumptions, and cancellation semantics.
- `service.py` coordinates public operations through constructor-injected dependencies. Root provisioning, IDs, timestamps, revisions, namespace atomicity, and hierarchy enforcement belong to the namespace driver. Content puts must complete before references are published. The service does not eagerly delete old or unpublished objects.

## Current boundary

Both production backends run the same parametrized public-interface acceptance and contract tests. Test support only records public calls and translates the domain DSL; it no longer supplies a parallel filesystem implementation. There are no REST/MCP entrypoints, authorization wiring, or application composition here; production never imports test support.

The initial H01/H02/H05 and E05 scenarios remain green. Adapter contracts additionally cover names, collisions, parent kinds, missing nodes, detached metadata, revision conflicts, immutable content, interrupted streams, and shared-root concurrency. Local-only checks cover reopening, corruption, symlink rejection, atomic publication failure, multiprocess creation, and cancellation. Names must contain Unicode scalar values; unpaired surrogate code points fail consistently as invalid names.

Metadata replacement, moves, deletion, ownership/sharing, authorization, checksums, and deferred cleanup execution remain unimplemented. Current evidence and limits are recorded in `.atdd/features/virtual-filesystem/06-storage-adapters.md` at the repository root. The suite does not establish every scenario from the original design.
