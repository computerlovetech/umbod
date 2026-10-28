---
type: Software Module
title: "Configuration"
description: "Operator settings, validation and conversion into runtime application configuration."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [app.py](./app.py) — Runtime models, including independent filesystem content selection and upload limits.
- [build.py](./build.py) — Operator-to-runtime assembly and local filesystem content directory normalization.
- [defaults.py](./defaults.py) — Configuration defaults.
- [derive.py](./derive.py) — Configuration loading.
- [inspection.py](./inspection.py) — Redacted inspection.
- [operator.py](./operator.py) — Operator-facing settings.
- [personal_connection_policy.py](./personal_connection_policy.py) — Personal identity and OAuth policy resolution.
- [secret_derivation.py](./secret_derivation.py) — Secret derivation.
- [server_settings.py](./server_settings.py) — Server root-secret preflight.
- [validate.py](./validate.py) — Cross-field validation.

# Related documentation

- [Operator configuration](../../../../docs/operations/configuration.md) — Deployment settings, filesystem storage, authentication and personal identity policy.
