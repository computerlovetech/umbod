---
type: Software Module
title: "Downstream MCP REST"
description: "Downstream MCP administration with separately mounted personal-user and callback delivery."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [dependencies.py](./dependencies.py) — Request-scoped administration composition.
- [errors.py](./errors.py) — Public error adaptation.
- [oauth.py](./oauth.py) — Shared OAuth administration.
- [personal_connections/](./personal_connections/README.md) — Personal selection and durable OAuth.
- [personal_tools.py](./personal_tools.py) — Administrator tool-contract approval.
- [personal_validation.py](./personal_validation.py) — Secret-safe write validation.
- [routes.py](./routes.py) — Connector administration routes.
- [schemas.py](./schemas.py) — Administration transport models.

# Context not available from the code

- [Personal authorization specification](../../../../../../docs/operations/personal-downstream-mcp-authorization-specification.md) — Personal credential ownership remains separate from shared administrator OAuth; package nesting does not merge authentication boundaries.
