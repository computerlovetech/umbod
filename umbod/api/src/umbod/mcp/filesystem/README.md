---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for namespace-aware browsing, content, updates, file deletion and individual file/folder sharing."
---

# Modules

- [Filesystem browsing](./browsing/README.md) — Namespace-aware browse operations, schemas and readable results.
- [Filesystem deletion](./deletion/README.md) — Human approval and revision-checked file deletion.
- [Filesystem sharing](./sharing/README.md) — Individual item sharing and recipient discovery.
- [Filesystem node presentation](./nodes/README.md) — Caller-specific node enrichment, response models and links.
- [Filesystem uploads](./uploads/README.md) — One-shot uploads and upload session adapters.
- [Filesystem discovery](./discovery/README.md) — Caller-specific discovery authorization and synchronized runtime state.

# Files

- [__init__.py](./__init__.py) — Public server composition interface for tool/resource registration, caller capture, services, discovery and deletion approval.
- [registration.py](./registration.py) — Built-in response metadata, explicit output schemas, observed filesystem tools, and native file links.
- [factory.py](./factory.py) — Operation-local service composition.
- [ports.py](./ports.py) — Caller capture and operation-local service factory contracts.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [argument_errors.py](./argument_errors.py) — Bounded field-level argument guidance derived from declared schemas, without submitted values or dynamic keys.
- [errors.py](./errors.py) — Safe public failures with recovery guidance and authorization-denial classification, without hidden-node disclosure.
- [resources.py](./resources.py) — Authorized current-file resources with MIME-aware text/blob content, captured revisions and the configured preview read limit.
- [update.py](./update.py) — Revision-checked moves within namespaces, preserving item grants and reevaluating folder inheritance.

# Related links

- [ADR-012: Permission-aware MCP tool visibility](../../../../../project/architecture-records/ADR-012-permission-aware-mcp-tool-visibility.md) — Proposed: caller-specific tool visibility and independent invocation authorization.
- [ADR-015: Self-describing built-in MCP tool contracts](../../../../../project/architecture-records/ADR-015-self-describing-built-in-mcp-tool-contracts.md) — Filesystem tool input schemas and operation descriptions.
- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Shared namespace administration](../../rest/filesystem_administration/README.md) — Administrator-managed shared namespaces and registered group read or read/write access.
- [Filesystem HTTP boundary](../../rest/filesystem/README.md) — REST session transfers and downloads remain separate from the one-shot MCP upload contract.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Shared upload lifecycle and one-shot MCP boundary.
