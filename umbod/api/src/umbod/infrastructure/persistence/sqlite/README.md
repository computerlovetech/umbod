---
type: Software Module
title: SQLite persistence
description: SQLite query adaptation, provider-injected database operations and backend-local resource assembly.
---

# Files

- [database.py](./database.py) — SQL sessions and transactions using a required injected connection provider.
- [factories.py](./factories.py) — Matching SQLite database and provider assembly with explicit pooled and unpooled choices.
- [compiler.py](./compiler.py) — Typed persistence query compilation to SQLite statements.
- [identifiers.py](./identifiers.py) — SQLite identifier validation and quoting.
- [value_mapping.py](./value_mapping.py) — Typed column encoding and SQLite value decoding.
- [schema_preparation.py](./schema_preparation.py) — Application schema upgrades and legacy metadata preparation.
- [schema_validation.py](./schema_validation.py) — Validation of non-reusing generated integer key schemas.
- [__init__.py](./__init__.py) — SQLite adapter exports.

# Related links

- [Connection infrastructure](../../connections/README.md) — Managed leases, pool lifecycle and shared SQLite connection configuration.
- [Persistence runtime](../runtime.py) — Application-owned provider startup, schema readiness and draining shutdown.
