---
type: Software Module
title: "Configuration"
description: "Operator settings, validation and conversion into runtime application configuration."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [app.py](./app.py) — Runtime configuration models.
- [build.py](./build.py) — Operator-to-runtime assembly.
- [defaults.py](./defaults.py) — Configuration defaults.
- [derive.py](./derive.py) — Configuration loading.
- [inspection.py](./inspection.py) — Redacted inspection.
- [operator.py](./operator.py) — Operator-facing settings.
- [personal_connection_policy.py](./personal_connection_policy.py) — Personal identity and OAuth policy resolution.
- [secret_derivation.py](./secret_derivation.py) — Secret derivation.
- [server_settings.py](./server_settings.py) — Server root-secret preflight.
- [validate.py](./validate.py) — Cross-field validation.

# Context not available from the code

- [Operator configuration](../../../../docs/operations/configuration.md) — Deployment settings, provider issuer/audience requirements and personal identity policy; preserve the identity namespace across restarts to retain ownership.
