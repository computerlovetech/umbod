---
type: Software Module
title: "Filesystem content"
description: "Authorized streaming uploads and downloads over independent content storage."
---

# Files

- [__init__.py](./__init__.py) — Public content operation exports.
- [ports.py](./ports.py) — Caller-aware upload and download contract.
- [models.py](./models.py) — Download summary, byte stream and size.
- [service.py](./service.py) — Bounded uploads and atomic authorized namespace publication.
- [errors.py](./errors.py) — Upload byte-limit failure.
