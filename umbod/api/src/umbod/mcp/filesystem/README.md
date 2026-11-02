---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for authorized filesystem browsing, content reads, creation, uploads, file deletion, and direct group/user sharing."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [approval.py](./approval.py) — Mandatory human deletion confirmation through elicitation or signed, single-use continuations.
- [approval_state.py](./approval_state.py) — Expiring deletion approval bound to the authenticated caller, client, file and revision.
- [argument_errors.py](./argument_errors.py) — Bounded field-level argument guidance derived from declared schemas, without submitted values or dynamic keys.
- [authorization.py](./authorization.py) — Caller-specific tool and resource-template visibility with independent endpoint-scope restrictions.
- [browsing.py](./browsing.py) — Observed home, ls, tree and stat operations with caller permissions and direct policy visibility.
- [browsing_models.py](./browsing_models.py) — Discriminated operation inputs and MCP output schemas with required node sharing metadata.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [deletion.py](./deletion.py) — Human-approved, revision-checked removal of one file and its policies, never directories or stored bytes.
- [errors.py](./errors.py) — Safe public failures with recovery guidance and authorization-denial classification, without hidden-node disclosure.
- [factory.py](./factory.py) — Operation-local service composition.
- [links.py](./links.py) — Canonical current-file URIs and native resource links alongside structured tool results.
- [models.py](./models.py) — Required authorized/restricted sharing projections, enriched nodes, child envelopes, and deletion contracts.
- [ports.py](./ports.py) — Caller, service factory and mandatory deletion approval contracts.
- [resources.py](./resources.py) — Authorized current-file resources with MIME-aware text/blob content, captured revisions, and complete reads capped at 1 MiB.
- [registration.py](./registration.py) — Built-in response metadata, explicit output schemas, observed filesystem tools, and native file links.
- [rendering.py](./rendering.py) — Readable listings with JSON-escaped untrusted descriptions, explicit visibility and expansion limits.
- [runtime.py](./runtime.py) — Caller-neutral authorization snapshots hydrated at startup and reconciled through durable events.
- [sharing.py](./sharing.py) — Invocation-local core access and manageable-sharing enrichment for full node results.
- [sharing_models.py](./sharing_models.py) — Strict unified recipient-search scopes and sharing inputs with legacy group mutation compatibility.
- [sharing_tools.py](./sharing_tools.py) — Node-authorized group/user recipient search and idempotent additive direct-node sharing.
- [update.py](./update.py) — Strict top-level revision-checked rename, move and metadata changes with shared REST validation.
- [upload.py](./upload.py) — One-shot private uploads capped at 10,485,760 decoded bytes or the lower server limit; no chunking or idempotent retries.
- [upload_models.py](./upload_models.py) — Bounded UTF-8 and canonical padded base64 inputs; results never echo content.
- [upload_session_models.py](./upload_session_models.py) — Begin/complete inputs, capability-only single PUT instructions and verified publication receipts.
- [upload_sessions.py](./upload_sessions.py) — Additive begin and idempotent complete tools using the configured public API origin and native resource links.

# Related links

- [Capability upload protocol](../../../../../docs/reference/filesystem-upload-transfers.md) — Larger HTTP transfers without MCP bearer delegation; crashed claims are not recovered.

- [ADR-012](../../../../../project/architecture-records/ADR-012-permission-aware-mcp-tool-visibility.md) — At-least-one-authorized-operation visibility with independent invocation authorization.
- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Root-access administration](../../rest/filesystem_administration/README.md) — Root initialization and grants are trusted administration, not MCP bootstrap; local test identities gain no implicit access.
- [Filesystem HTTP boundary](../../rest/filesystem/README.md) — REST session transfers and downloads remain separate from the one-shot MCP upload contract.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Shared upload lifecycle and one-shot MCP boundary.
