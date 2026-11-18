---
type: Software Module
title: Core administrator operations
description: Transport-neutral administrator discovery, inspection and changes.
---

# Files

- [__init__.py](./__init__.py) — Public core administrator contracts.
- [operations.py](./operations.py) — Authorized discovery, inspection and changes over existing domain services.
- [models.py](./models.py) — Validated user search and group permission patch contracts.
- [ports.py](./ports.py) — Dependencies for group, permission and identity directory operations.
- [connector_inventory.py](./connector_inventory.py) — Connector inventory projection without credentials or upstream requests.
- [connector configuration models](./connector_configuration/models.py) — Capability configuration requests and state.
