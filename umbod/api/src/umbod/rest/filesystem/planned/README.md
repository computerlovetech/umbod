---
type: Software Module
title: "Planned filesystem HTTP contracts"
description: "Design-only filesystem routes that expose unavailable contracts rather than implemented storage capabilities."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Verified-caller unavailable responses.
- [models.py](./models.py) — Planned boundary requests and errors.
- [routes.py](./routes.py) — Planned endpoint and OpenAPI declarations.
- [uploads.py](./uploads.py) — Legacy JSON and planned multipart dispatch.

# Context not available from the code

- [Implemented filesystem boundary](../README.md) — Browsing and empty creation remain distinct from these plans.
- [ADR-006](../../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Storage boundary; planned HTTP contracts do not claim completed content or authorization capabilities.

Owned/shared listings, breadcrumbs, content operations, multipart upload, rename/move, deletion and access editing are design-only. Legacy empty-file creation is not an upload substitute. Revision-checked mutations, pagination and server-evaluated browser capabilities are future contracts; clients must not infer support from OpenAPI placeholders.
