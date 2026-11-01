---
type: Software Module
title: Backend tests
description: Backend behavior, adapter and architecture tests with shared runtime and persistence fixtures.
---

# Files

- [__init__.py](./__init__.py)
- [conftest.py](./conftest.py) — Shared isolation and connector fixtures.
- [mcp_fixtures.py](./mcp_fixtures.py) — MCP application fixtures.
- [mcp_telemetry_fixtures.py](./mcp_telemetry_fixtures.py) — Typed recording telemetry and listener test adapters.
- [persistence_runtime.py](./persistence_runtime.py) — Persistence runtime fixtures.
- [test_persistence_fixtures.py](./test_persistence_fixtures.py) — Fixture isolation checks.
- [test_semgrep_test_practices.py](./test_semgrep_test_practices.py) — Exhaustive directory rule cases and focused external-file path-scope checks.
- [connectors](./connectors/) — Connector plugin fixtures.
- [core](./umbod/core/) — Core behavior and contract tests.
- [deployment](./deployment/) — Deployment contracts.
- [hosting](./hosting/) — Hosting composition checks.
- [infrastructure](./umbod/infrastructure/) — Infrastructure checks.
- [mcp](./umbod/mcp/) — MCP behavior and contract tests.
- [Sharing discovery tests](./umbod/mcp/filesystem/test_recipient_search.py) — Strict unified search, node authority, directory privacy, and fixed result limits.
- [messaging](./messaging/) — Shared messaging tests.
- [rest](./umbod/rest/) — REST behavior and contract tests.
- [support](./support/README.md) — Test-only adapters and acceptance drivers.
- [umbod](./umbod/) — Application module tests.

# Verification

- [Repository verification instructions](../../../AGENTS.md#tests-and-static-checks) — Capped parallel suites, isolated test resources, and serial live-runtime checks.
- [Shared Semgrep rules](../../../.semgrep.yml) — Cross-cutting checks retained for source and test code.
- [Production design rules](../../../.semgrep/production-design.yml) — Source-only design checks that exclude test files and support trees.
- [Test correctness rules](../../../.semgrep/test-correctness.yml) — Mutable-default checks and contextual patching and empty-container fallback warnings.
- [Semgrep scan scope](../../../.semgrepignore) — Includes test trees while excluding dependencies and build output.
- [Filesystem acceptance tests](./umbod/core/filesystem/) — Namespace, ownership, authorization and persistence acceptance coverage.
- [Kind runtime checks](../../tests/kind-runtime/README.md) — Running-service verification, separate from unit and adapter tests. Metrics acceptance tests do not establish deployment-level network isolation; verify that against deployed services.
