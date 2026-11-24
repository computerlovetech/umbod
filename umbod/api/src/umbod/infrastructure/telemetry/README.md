---
type: Software Module
title: Telemetry infrastructure
description: Independent analytics runtime composition and backend implementations.
---

# Files

- [Exports](__init__.py) — Configured analytics runtime composition entrypoint.
- [Composition](composition.py) — Configured selection and disabled analytics behavior.
- [Backfill composition](backfill_composition.py) — Opens the configured analytics archive without running server maintenance.
- [Replay composition](replay_composition.py) — Internal preview and apply factory; initialize the configured analytics runtime separately before replay.
- [SQLite](sqlite/README.md) — Independent analytics storage and SQL aggregation.
