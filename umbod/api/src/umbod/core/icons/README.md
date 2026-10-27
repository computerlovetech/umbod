---
type: Software Module
title: "Icon discovery"
description: "Reusable connector icon discovery through strategy and HTTP ports."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [adapters/](./adapters/) — HTTP implementations.
- [http_models.py](./http_models.py) — Bounded HTTP data.
- [http_ports.py](./http_ports.py) — HTTP fetching contract.
- [in_memory.py](./in_memory.py) — Scripted discovery adapter.
- [models.py](./models.py) — Discovery requests and outcomes.
- [ports.py](./ports.py) — Discovery strategy contracts.
- [service.py](./service.py) — Strategy orchestration.
- [strategies.py](./strategies.py) — Advertised icon selection.
- [web_strategies.py](./web_strategies.py) — Website favicon strategies.
