---
type: Software Module
title: "Configuration"
description: "Operator settings, validation and conversion into runtime application configuration."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [app.py](./app.py) — Runtime models, including validated local, in-memory, and S3 filesystem content selection.
- [build.py](./build.py) — Operator-to-runtime assembly, S3 backend selection, and local content directory normalization.
- [defaults.py](./defaults.py) — Configuration defaults.
- [derive.py](./derive.py) — Configuration loading.
- [identity_policy.py](./identity_policy.py) — Shared local identity eligibility and filesystem managed-issuer selection.
- [inspection.py](./inspection.py) — Redacted inspection.
- [operator.py](./operator.py) — Operator-facing settings and fail-closed filesystem backend combinations.
- [personal_connection_policy.py](./personal_connection_policy.py) — Personal identity and OAuth policy resolution.
- [secret_derivation.py](./secret_derivation.py) — Secret derivation.
- [server_settings.py](./server_settings.py) — Server root-secret preflight.
- [validate.py](./validate.py) — Cross-field validation.

# Related documentation

- [Operator configuration](../../../../docs/operations/configuration.md) — Deployment settings, filesystem storage, authentication and personal identity policy.
