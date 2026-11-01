---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for authorized filesystem browsing, content reads, creation, uploads, file deletion, and direct group/user sharing."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [authorization.py](./authorization.py) — Caller-specific tool visibility and request-local eligibility reuse across tool listing and lookup.
- [browsing.py](./browsing.py) — Observed ls, tree and stat operations through shared core exploration.
- [browsing_models.py](./browsing_models.py) — Discriminated operation inputs and MCP output schemas with required node sharing metadata.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [deletion.py](./deletion.py) — Revision-checked removal of one file and its policies, never directories or stored bytes.
- [errors.py](./errors.py) — Safe public failures preserving authorization-denial classification for invocation and audit telemetry.
- [factory.py](./factory.py) — Operation-local service composition.
- [models.py](./models.py) — Required authorized/restricted sharing projections, enriched nodes, child envelopes, and deletion contracts.
- [ports.py](./ports.py) — Caller and service factory contracts.
- [read.py](./read.py) — Complete, authorized UTF-8 or base64 reads capped at 1 MiB, with explicit budgets and snapshot revisions; never truncated.
- [read_models.py](./read_models.py) — Strict read budgets and bounded encoded output schemas.
- [registration.py](./registration.py) — Filesystem tool registration, retaining existing browsing and creation tools.
- [rendering.py](./rendering.py) — Readable filesystem listings with explicit visibility and expansion limits.
- [runtime.py](./runtime.py) — Caller-neutral authorization snapshots hydrated at startup and reconciled through durable events.
- [sharing.py](./sharing.py) — Invocation-local batch enrichment of returned nodes through core sharing; no policy decisions or discovery queries.
- [sharing_models.py](./sharing_models.py) — Strict unified recipient-search scopes and sharing inputs with legacy group mutation compatibility.
- [sharing_tools.py](./sharing_tools.py) — Node-authorized group/user recipient search and idempotent additive direct-node sharing.
- [upload.py](./upload.py) — One-shot private uploads capped at 10,485,760 decoded bytes or the lower server limit; no chunking or idempotent retries.
- [upload_models.py](./upload_models.py) — Bounded UTF-8 and canonical padded base64 inputs; results never echo content.

# Related links

- [ADR-012](../../../../../project/architecture-records/ADR-012-permission-aware-mcp-tool-visibility.md) — At-least-one-authorized-operation visibility with independent invocation authorization.
- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Root-access administration](../../rest/filesystem_administration/README.md) — Root initialization and grants are trusted administration, not MCP bootstrap; local test identities gain no implicit access.
- [Filesystem HTTP boundary](../../rest/filesystem/README.md) — REST session transfers and downloads remain separate from the one-shot MCP upload contract.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Shared upload lifecycle and one-shot MCP boundary.
