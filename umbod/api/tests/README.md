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
- [core](./umbod/core/) — Core behavior and contract tests.
- [deployment](./deployment/) — Deployment contracts.
- [hosting](./hosting/) — Hosting composition checks.
- [infrastructure](./umbod/infrastructure/) — Infrastructure checks.
- [mcp](./umbod/mcp/) — MCP behavior and contract tests.
- [messaging](./messaging/) — Shared messaging tests.
- [rest](./umbod/rest/) — REST behavior and contract tests.
- [support](./support/) — Acceptance drivers and test support.
- [umbod](./umbod/) — Application module tests.

# Context not available from the code

- [Repository verification instructions](../../../AGENTS.md#tests-and-static-checks) — Capped parallel suite commands and serial debugging.
- Tests must collect deterministically and isolate writable files, databases and network listeners across worker processes. Kind and live-runtime checks remain serial.
- [Filesystem acceptance tests](./umbod/core/filesystem/) — Namespace, ownership, authorization and persistence acceptance coverage.
- [Kind runtime checks](../../tests/kind-runtime/README.md) — Running-service verification, separate from unit and adapter tests. Metrics acceptance tests do not establish deployment-level network isolation; verify that against deployed services.
