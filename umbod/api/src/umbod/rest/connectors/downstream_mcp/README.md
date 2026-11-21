---
type: Software Module
title: "Downstream MCP REST"
description: "Downstream MCP administration with separately mounted personal-user and callback delivery."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [dependencies.py](./dependencies.py) — Request-scoped administration composition.
- [endpoint_access.py](./endpoint_access.py) — Admin pre-registration checks for anonymous MCP access and OAuth metadata.
- [errors.py](./errors.py) — Public error adaptation.
- [oauth.py](./oauth.py) — Shared OAuth administration.
- [personal_connections/](./personal_connections/README.md) — Personal selection and durable OAuth.
- [personal_oauth_metadata.py](./personal_oauth_metadata.py) — Administrator-only bounded, no-store creation discovery with request-scoped provider composition.
- [personal_oauth_setup.py](./personal_oauth_setup.py) — Administrator-only bounded discovery and validation endpoints.
- [personal_tools.py](./personal_tools.py) — Administrator tool-contract approval.
- [personal_validation.py](./personal_validation.py) — Secret-safe write validation.
- [registry.py](./registry.py) — Administrator search of the official MCP registry.
- [preview_validation.py](./preview_validation.py) — Bounded request bodies and sanitized errors for no-store previews.
- [routes.py](./routes.py) — Connector administration routes.
- [schemas.py](./schemas.py) — Administration transport models.
