---
type: Software Module
title: Backend tests
description: Backend behavior, adapter and architecture tests with shared runtime and persistence fixtures.
---

# Files

- [__init__.py](./__init__.py)
- [conftest.py](./conftest.py) — Shared isolation and connector fixtures.
- [mcp_fixtures.py](./mcp_fixtures.py) — MCP application fixtures.
- [persistence_runtime.py](./persistence_runtime.py) — Persistence runtime fixtures.
- [test_persistence_fixtures.py](./test_persistence_fixtures.py) — Fixture isolation checks.
- [connectors](./connectors/) — Connector plugin fixtures.
- [core](./core/) — Core test utilities.
- [deployment](./deployment/) — Deployment contracts.
- [hosting](./hosting/) — Hosting composition checks.
- [infrastructure](./infrastructure/) — Infrastructure checks.
- [mcp](./mcp/) — MCP test utilities.
- [messaging](./messaging/) — Shared messaging tests.
- [rest](./rest/) — REST test utilities.
- [support](./support/) — Acceptance drivers and test support.
- [umbod](./umbod/) — Application module tests.

# Context not available from the code

- [Repository verification instructions](../../../AGENTS.md#tests-and-static-checks) — Capped parallel suite commands and serial debugging.
- Tests must collect deterministically and isolate writable files, databases and network listeners across worker processes. Kind and live-runtime checks remain serial.
- [Filesystem acceptance plan](../../../.atdd/features/filesystem/04-acceptance-test-plan.md) — Original scenario mapping.
- [Database namespace and policy scope](../../../.atdd/features/filesystem/10-database-namespace-and-policies.md) — Ownership and persistence acceptance boundaries.
- [Kind runtime checks](../../tests/kind-runtime/README.md) — Running-service verification, separate from unit and adapter tests. Metrics acceptance tests do not establish deployment-level network isolation; verify that against deployed services.
