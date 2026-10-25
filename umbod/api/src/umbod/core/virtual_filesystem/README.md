# Virtual filesystem

**Module responsibility:** Standalone storage-independent filesystem coordination. This initial slice supports discovery of a driver-provided shared root, directory/file creation, node retrieval, child listing, and streaming content reads/writes.

**Public entrypoint:** Import models, ports, and `VirtualFilesystem` from `umbod.core.virtual_filesystem`.

## Files

- `models.py` defines Pydantic node, metadata, immutable-content reference, and node-kind boundary values. Fields are explicit; RootParent, EmptyContent, and UnspecifiedContentType model absence as named states rather than nullable values. These states replace the original design's None representations.
- `ports.py` defines namespace and content dependency protocols and the byte-stream type. The namespace publication operation replaces a complete content reference with an expected revision; general metadata patches and content clearing are not part of this initial port surface.
- `service.py` coordinates public operations through constructor-injected dependencies. Root provisioning, IDs, timestamps, revisions, namespace atomicity, and hierarchy enforcement belong to the namespace driver. Content puts must complete before references are published. The service does not eagerly delete old or unpublished objects.

## Current boundary

There are no concrete storage adapters, REST/MCP entrypoints, authorization wiring, or application composition here. Acceptance support and dependency doubles remain under the test tree; production never imports them.

The initial H01/H02/H05 acceptance slice and the E05 empty-file regression are green. The remaining 43 scenarios, including full invalid-operation handling, namespace concurrency contracts, metadata replacement, moves, deletion, ownership/sharing contracts, and retained-content lifecycle evidence, are deferred in `.atdd/features/virtual-filesystem/04-acceptance-test-plan.md` at the repository root. Checksums are not yet part of the content-reference model. This initial module is not a complete production-ready filesystem or proof of storage-driver conformance.
