---
type: Software Module
title: "Personal connections REST"
description: "Owner-scoped downstream MCP selection, authorization and discovery delivery."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [authorization.py](./authorization.py) — Authorization status projection.
- [dependencies.py](./dependencies.py) — Verified owner and inventory dependencies.
- [oauth_callback.py](./oauth_callback.py) — State-bound public callback.
- [oauth_callback_app.py](./oauth_callback_app.py) — Public callback application composition.
- [oauth_dependencies.py](./oauth_dependencies.py) — Authorization and callback composition.
- [oauth_diagnostics.py](./oauth_diagnostics.py) — Request-scoped OAuth observers over the explicitly composed application failure channel.
- [oauth_policy.py](./oauth_policy.py) — Explicit OAuth feature policy and settings-backed dependency.
- [oauth_routes.py](./oauth_routes.py) — Authorization attempt routes.
- [oauth_schemas.py](./oauth_schemas.py) — Authorization transport models.
- [refresh_dependencies.py](./refresh_dependencies.py) — Refresh service composition.
- [refresh_routes.py](./refresh_routes.py) — Owner authorization refresh.
- [routes.py](./routes.py) — Catalogue, enablement and disconnect.
- [discovery.py](./discovery.py) — Credential-free availability snapshots for already-authorized owner selections.
- [schemas.py](./schemas.py) — Secret-free user projections.
- [tools.py](./tools.py) — Owner-private tool discovery.
