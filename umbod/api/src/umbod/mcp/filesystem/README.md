---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for authorized filesystem browsing, node creation, and one-shot uploads."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [authorization.py](./authorization.py) — Root-endpoint tool eligibility.
- [browsing.py](./browsing.py) — Observed ls, tree and stat operations through shared core exploration.
- [browsing_models.py](./browsing_models.py) — Discriminated operation inputs and shared output schemas.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [errors.py](./errors.py) — Safe public failures.
- [factory.py](./factory.py) — Operation-local service composition.
- [models.py](./models.py) — Transport metadata and child envelopes.
- [ports.py](./ports.py) — Caller and service factory contracts.
- [registration.py](./registration.py) — Filesystem tool registration, retaining existing browsing and creation tools.
- [rendering.py](./rendering.py) — Readable filesystem listings with explicit visibility and expansion limits.
- [upload.py](./upload.py) — One-shot private uploads capped at 1,048,576 decoded bytes or the lower server limit; no chunking or idempotent retries.
- [upload_models.py](./upload_models.py) — Bounded UTF-8 and canonical padded base64 inputs; results never echo content.

# Related links

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Root-access administration](../../rest/filesystem_administration/README.md) — Root initialization and grants are trusted administration, not MCP bootstrap; local test identities gain no implicit access.
- [Filesystem HTTP boundary](../../rest/filesystem/README.md) — REST session transfers and downloads remain separate from the one-shot MCP upload contract.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Shared upload lifecycle and one-shot MCP boundary.
