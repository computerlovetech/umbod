---
type: Software Module
title: Built-in MCP responses
description: Built-in MCP guidance rendering and versioned client metadata without changing domain payload schemas.
---

# Files

- [__init__.py](./__init__.py) — Response adapter package boundary.
- [adapter.py](./adapter.py) — Built-in result metadata, safe failure mapping, and unchanged connector passthrough.
- [arguments.py](./arguments.py) — Schema-approved argument paths, bounded issues, and safe generic corrections.
- [ports.py](./ports.py) — Response adaptation contract for observed tool execution.
- [progress.py](./progress.py) — Invocation-local admission and completion evidence with nested scope restoration.
- [recovery.py](./recovery.py) — Approved operation-specific inspection and recovery instructions without reflecting submitted values.
- [rendering.py](./rendering.py) — Deterministic DTO-to-text guidance and compatible serialized success payloads.
- [validation.py](./validation.py) — Pre-admission argument validation before classified invocation failure publication.

# Related links

- [ADR-014](../../../../../project/architecture-records/ADR-014-built-in-mcp-response-guidance.md) — Built-in content/metadata policy, response construction, and confirmation guidance.
- [Core responses](../../core/responses/README.md) — Transport-neutral metadata DTOs and construction rules.
- [Observed registration](../tools/registration.py) — Explicit built-in opt-in and successful-output validation.
- [Response middleware](../middleware/response_metadata.py) — HTTP correlation and conversation-visible error context.
- [Application diagnostics](../../../../../docs/operations/application-diagnostics.md) — Privacy, operation-state, and retry contracts.
