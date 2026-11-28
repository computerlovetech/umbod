---
type: Software Module
title: "Configuration"
description: "Operator settings, validation and conversion into runtime application configuration."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [app.py](./app.py) — Runtime models, conditional dedicated MCP administrator validation, advertised collector URLs, and filesystem content selection.
- [build.py](./build.py) — Operator-to-runtime assembly, S3 backend selection, and local content directory normalization.
- [defaults.py](./defaults.py) — Configuration defaults.
- [derive.py](./derive.py) — Configuration loading.
- [group_membership.py](./group_membership.py) — Verified OAuth membership snapshots from administrator-saved mappings and configured issuer and claim selectors.
- [identity_policy.py](./identity_policy.py) — Shared local identity eligibility and filesystem managed-issuer selection.
- [inspection.py](./inspection.py) — Redacted inspection.
- [operator.py](./operator.py) — Operator settings, validated preview byte limits, public collector URLs and fail-closed filesystem backend combinations.
- [personal_connection_policy.py](./personal_connection_policy.py) — Personal identity and OAuth policy resolution.
- [secret_derivation.py](./secret_derivation.py) — Secret derivation.
- [server_settings.py](./server_settings.py) — Server root-secret preflight.
- [system_settings.py](./system_settings.py) — Deployment default for the MCP file deletion approval setting.
- [usage.py](./usage.py) — Bounded personal usage collection settings and queue/batch validation.
- [validate.py](./validate.py) — Cross-field validation.
- [telemetry.py](./telemetry.py) — Collector-only settings and security validation independent of REST and MCP configuration.
