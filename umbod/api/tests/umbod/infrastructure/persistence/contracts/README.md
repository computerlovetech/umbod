---
type: Software Module
title: Persistence adapter contracts
description: Shared database-port behavior verified against real memory and SQLite adapters.
---

# Files

- [__init__.py](./__init__.py) — Keeps relocated adapter tests in a distinct collection namespace.
- [conftest.py](./conftest.py) — Two-driver adapter selection for physical contract coverage.
- [test_database_contract_atomicity.py](./test_database_contract_atomicity.py) — Concurrent writes and transactional failure isolation.
- [test_database_contract_codec_failures.py](./test_database_contract_codec_failures.py) — Codec rejection, unchanged records and recovery.
- [test_database_contract_queries.py](./test_database_contract_queries.py) — Typed predicates, scoped ordering and projections.
- [test_database_contract_transactions.py](./test_database_contract_transactions.py) — Exception, cancellation and serialized transaction guarantees.
- [test_database_contract_values.py](./test_database_contract_values.py) — Canonical scalar and JSON storage semantics.
- [test_database_port.py](./test_database_port.py) — Generated keys, typed reads and mutation behavior.
- [test_non_reusing_integer_keys.py](./test_non_reusing_integer_keys.py) — Committed generated-key history and rollback policy.
- [test_read_plan.py](./test_read_plan.py) — Deferred read execution, batching and snapshot results.
- [test_read_session_contract.py](./test_read_session_contract.py) — Read-only session and transaction behavior.
