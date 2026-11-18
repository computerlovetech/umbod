---
type: Software Module
title: "Filesystem uploads"
description: "One-shot uploads and upload session adapters."
---

# Files

- [__init__.py](./__init__.py) — Public upload tools and command exports.
- [one_shot.py](./one_shot.py) — Namespace-governed one-shot uploads capped at 10,485,760 decoded bytes or the lower server limit; no chunking or idempotent retries.
- [one_shot_models.py](./one_shot_models.py) — Bounded UTF-8 and canonical padded base64 inputs; results never echo content.
- [sessions.py](./sessions.py) — Default presigned S3 or delegated API begin instructions, durable progress markers and verified completion with native file links.
- [session_models.py](./session_models.py) — Begin/complete inputs, sensitive single-PUT instructions and verified publication receipts.
