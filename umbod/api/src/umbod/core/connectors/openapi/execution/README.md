---
type: Software Module
title: "OpenAPI execution"
description: "Approved OpenAPI operation execution through authentication, outbound transport and response normalization."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [authentication.py](./authentication.py) — Trusted outbound authorization.
- [http_adapters.py](./http_adapters.py) — Outbound HTTP policy.
- [parameter_serialization.py](./parameter_serialization.py) — OpenAPI parameter encoding.
- [request_values.py](./request_values.py) — Request value preparation.
- [service.py](./service.py) — Execution pipeline coordination.
