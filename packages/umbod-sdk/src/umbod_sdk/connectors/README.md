---
type: Software Module
title: Connectors
description: Public connector authoring contracts, capability metadata and plugin discovery.
---

# Files

- [__init__.py](./__init__.py) — Public connector exports.
- [capability_description.py](./capability_description.py) — Capability descriptions.
- [declaration.py](./declaration.py) — Shared connector declarations for CPython and Monty.
- [discovery.py](./discovery.py) — Connector package discovery.
- [http.py](./http.py) — Portable async request context for connector handlers.
- [models.py](./models.py) — Configuration check results.
- [output_schema.py](./output_schema.py) — Output schema definitions.
- [plugin_api.py](./plugin_api.py) — Public connector authoring API.
- [proxies.py](./proxies.py) — Model serialization and schema contracts.
- [types.py](./types.py) — Plugin registration and operation contracts.
- [uploaded_file.py](./uploaded_file.py) — File input contract.
- [api](./api/) — Connector definitions, parameters and registration.
- [manifest.py](./api/manifest.py) — Host-side validation of explicit schemas and portable manifests.
- [HTTP request boundary](./api/http.py) — Validates relative requests and upstream response contracts over an injected transport.
- [HTTP invocation scope](./api/http_scope.py) — Owns and cancels asynchronous host requests for one invocation.

# Related guidance

- [Connector authoring skill](../skills/draft-agent-connector/SKILL.md) — Authoring workflow and contract reference.
