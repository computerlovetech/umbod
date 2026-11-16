---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for namespace-aware browsing, content, updates, file deletion and individual file/folder sharing."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [approval.py](./approval.py) — Mandatory human deletion confirmation through elicitation or signed, single-use continuations.
- [approval_state.py](./approval_state.py) — Expiring deletion approval bound to the authenticated caller, client, file and revision.
- [argument_errors.py](./argument_errors.py) — Bounded field-level argument guidance derived from declared schemas, without submitted values or dynamic keys.
- [authorization.py](./authorization.py) — Caller-specific tool and resource-template visibility with independent endpoint-scope restrictions.
- [browsing.py](./browsing.py) — Personal/shared namespace listing and observed home, ls, tree and stat operations.
- [browsing_scope.py](./browsing_scope.py) — Personal namespace defaults for root and absolute-path browse targets.
- [browsing_models.py](./browsing_models.py) — Discriminated operation inputs and namespace-aware MCP output schemas.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [deletion.py](./deletion.py) — Human-approved, revision-checked removal of one file and its policies, never directories or stored bytes.
- [errors.py](./errors.py) — Safe public failures with recovery guidance and authorization-denial classification, without hidden-node disclosure.
- [factory.py](./factory.py) — Operation-local service composition.
- [links.py](./links.py) — Configured authenticated browser view URLs and canonical current-file MCP resource links.
- [models.py](./models.py) — Node response view URLs, manageable sharing metadata, child envelopes and deletion contracts.
- [ports.py](./ports.py) — Caller, service factory and mandatory deletion approval contracts.
- [resources.py](./resources.py) — Authorized current-file resources with MIME-aware text/blob content, captured revisions and the configured preview read limit.
- [registration.py](./registration.py) — Built-in response metadata, explicit output schemas, observed filesystem tools, and native file links.
- [rendering.py](./rendering.py) — Readable listings with JSON-escaped untrusted descriptions, explicit visibility and expansion limits.
- [runtime.py](./runtime.py) — Caller-neutral authorization snapshots hydrated at startup and reconciled through durable events.
- [sharing.py](./sharing.py) — Invocation-local caller access and manageable direct item-sharing enrichment.
- [sharing_models.py](./sharing_models.py) — Typed user/group recipient, search and additive share contracts.
- [sharing_tools.py](./sharing_tools.py) — Individual file/folder sharing and recipient discovery within namespace boundaries.
- [update.py](./update.py) — Revision-checked moves within namespaces, preserving item grants and reevaluating folder inheritance.
- [upload.py](./upload.py) — Namespace-governed one-shot uploads capped at 10,485,760 decoded bytes or the lower server limit; no chunking or idempotent retries.
- [upload_models.py](./upload_models.py) — Bounded UTF-8 and canonical padded base64 inputs; results never echo content.
- [upload_session_models.py](./upload_session_models.py) — Begin/complete inputs, sensitive single-PUT instructions and verified publication receipts.
- [upload_sessions.py](./upload_sessions.py) — Default presigned S3 or delegated API begin instructions, durable progress markers and verified completion with native file links.

# Related links


- [ADR-012](../../../../../project/architecture-records/ADR-012-permission-aware-mcp-tool-visibility.md) — At-least-one-authorized-operation visibility with independent invocation authorization.
- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Shared namespace administration](../../rest/filesystem_administration/README.md) — Administrator-managed shared namespaces and registered group read or read/write access.
- [Filesystem HTTP boundary](../../rest/filesystem/README.md) — REST session transfers and downloads remain separate from the one-shot MCP upload contract.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Shared upload lifecycle and one-shot MCP boundary.
