---
type: Software Module
title: "Filesystem exploration"
description: "Transport-neutral inspection, directory listing and bounded tree composition over authorized browsing."
---

# Files

- [__init__.py](./__init__.py) — Public exploration contracts and composition.
- [models.py](./models.py) — Strict targets, required limits and safe summary-only results.
- [ports.py](./ports.py) — Caller-supplied exploration operations without transport dependencies.
- [service.py](./service.py) — Deterministic depth-first traversal; output bounds do not bound database work or provide an atomic snapshot.

# Related links

- [Browsing](../README.md) — Permission-filtered low-level operations; independently shared nodes retain partial breadcrumbs.
- [Tests](../../../../../../tests/umbod/core/filesystem/browsing/exploration/) — Resolution, limits, hierarchy failures and validation behavior.
