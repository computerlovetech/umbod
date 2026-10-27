---
type: Software Module
title: "MCP filesystem"
description: "MCP adapters for authorized filesystem browsing and empty node creation."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [authorization.py](./authorization.py) — Root-endpoint tool eligibility.
- [caller.py](./caller.py) — Invocation caller capture.
- [claim_fields.py](./claim_fields.py) — Permission claim sources.
- [errors.py](./errors.py) — Safe public failures.
- [factory.py](./factory.py) — Operation-local service composition.
- [models.py](./models.py) — Transport metadata and child envelopes.
- [ports.py](./ports.py) — Caller and service factory contracts.
- [registration.py](./registration.py) — Filesystem tool registration.

# Context not available from the code

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage boundary.
- [Root-access administration](../../rest/filesystem_administration/README.md) — Root initialization and grants are trusted administration, not MCP bootstrap; local test identities gain no implicit access.
- [Planned HTTP contracts](../../rest/filesystem/planned/README.md) — Content, upload and mutation plans do not imply MCP support.
