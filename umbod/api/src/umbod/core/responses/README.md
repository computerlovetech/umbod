---
type: Software Module
title: Tool response metadata
description: Immutable response guidance, schema-version-1 identity metadata, recovery contracts, and audience-separated extension boundaries.
---

# Files

- [Public API](__init__.py) — Exported metadata types and factory.
- [Models](models.py) — Immutable guidance, bounded recovery/notices, conservative retry validation, and closed audience-specific extension DTOs.
- [Factory](factory.py) — Metadata construction with caller-supplied request and server identity.
- [Tests](../../../../tests/umbod/core/responses/) — Public construction, wire shape, validation, and immutability checks.

# Related links

- [ADR-014](../../../../../project/architecture-records/ADR-014-built-in-mcp-response-guidance.md) — Built-in response guidance, metadata separation, extension visibility, and confirmation boundaries.
