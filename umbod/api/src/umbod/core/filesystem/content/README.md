---
type: Software Module
title: "Filesystem content"
description: "Authorized uploads, streaming reads and direct-download delivery over independent content storage."
---

# Files

- [__init__.py](./__init__.py) — Public content operation exports.
- [ports.py](./ports.py) — Caller-aware upload and download contract.
- [models.py](./models.py) — Download summary, byte stream and size.
- [delivery.py](./delivery.py) — Optional external download port with validated, immutable requests and private URL instructions.
- [service.py](./service.py) — Authorized streaming reads and storage-neutral download delivery, bounded uploads and namespace publication.
- [errors.py](./errors.py) — Upload byte-limit failure.
