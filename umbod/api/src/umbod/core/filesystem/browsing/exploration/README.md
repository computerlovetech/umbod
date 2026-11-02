---
type: Software Module
title: "Filesystem exploration"
description: "Transport-neutral inspection, directory listing and bounded tree composition over authorized browsing."
---

# Files

- [__init__.py](./__init__.py) — Public exploration contracts and composition.
- [models.py](./models.py) — Strict targets, required limits and safe summary-only results.
- [ports.py](./ports.py) — Caller-supplied exploration operations without transport dependencies.
- [service.py](./service.py) — Shared inspection, complete folder/file browsing, bounded listings and deterministic depth-first traversal.
- [scoped.py](./scoped.py) — Request-local authorization and operation eligibility over scoped facts without content reads.

# Related links

- [Browsing](../README.md) — Permission-filtered low-level operations; independently shared nodes retain partial breadcrumbs.
- [Tests](../../../../../../tests/umbod/core/filesystem/browsing/exploration/) — Resolution, limits, hierarchy failures and validation behavior.
