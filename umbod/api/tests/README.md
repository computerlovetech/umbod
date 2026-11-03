---
type: Software Module
title: Backend tests
description: Backend behavior, adapter and architecture tests with shared runtime and persistence fixtures.
---

# Files

- [__init__.py](./__init__.py)
- [conftest.py](./conftest.py) — Worker-owned isolation directories with unique per-test database paths and shared connector fixtures.
- [mcp_fixtures.py](./mcp_fixtures.py) — MCP application fixtures.
- [mcp_telemetry_fixtures.py](./mcp_telemetry_fixtures.py) — Typed recording telemetry and listener test adapters.
- [persistence_runtime.py](./persistence_runtime.py) — In-memory runtimes for business tests and explicit SQLite runtimes for adapter integration.
- [test_persistence_fixtures.py](./test_persistence_fixtures.py) — Fixture isolation checks.
- [cli](./umbod/cli/) — CLI behavior tests aligned with the source CLI package.
- [config](./umbod/config/) — Runtime configuration tests.
- [core](./umbod/core/) — Core behavior and contract tests aligned with source modules.
- [Core connectors](./umbod/core/connectors/) — Native, downstream MCP and OpenAPI connector domain tests.
- [deployment](./deployment/) — Deployment contracts.
- [hosting](./umbod/hosting/) — Service composition and lifecycle checks.
- [infrastructure](./umbod/infrastructure/) — Infrastructure checks.
- [mcp](./umbod/mcp/) — MCP behavior and contract tests selected by this directory.
- [MCP connectors](./umbod/mcp/connectors/) — Connector transport tests grouped by source provider module.
- [Sharing discovery tests](./umbod/mcp/filesystem/test_recipient_search.py) — Strict unified search, node authority, directory privacy, and fixed result limits.
- [messaging](./messaging/) — Shared messaging tests.
- [rest](./umbod/rest/) — REST behavior and contract tests selected by this directory.
- [REST connectors](./umbod/rest/connectors/) — Connector route tests grouped by source provider module.
- [REST filesystem fixtures](./umbod/rest/filesystem/conftest.py) — Minimal route composition and explicit full-application integration fixtures.
- [MCP filesystem fixtures](./umbod/mcp/filesystem/conftest.py) — Fresh service state separated from optional server, tool and resource registration.
- [support](./support/README.md) — Test-only adapters and acceptance drivers.
- [umbod](./umbod/) — Application module tests.

# Verification

- [Repository verification instructions](../../../AGENTS.md#tests-and-static-checks) — Directory-targeted module suites, automatic worker selection, and live-runtime checks.
- [Shared Semgrep rules](../../../.semgrep.yml) — Cross-cutting checks retained for source and test code.
- [Production design rules](../../../.semgrep/production-design.yml) — Source-only design checks that exclude test files and support trees.
- [Test correctness rules](../../../.semgrep/test-correctness.yml) — Mutable-default checks and contextual patching and empty-container fallback warnings.
- [Semgrep scan scope](../../../.semgrepignore) — Includes test trees while excluding dependencies and build output.
- [Persistence contracts](./umbod/core/persistence/) — Shared parameterized behavior checks for in-memory and SQLite drivers.
- [Filesystem acceptance tests](./umbod/core/filesystem/) — Namespace, ownership and authorization behavior using in-memory database persistence.
- [Kind runtime checks](../../tests/kind-runtime/README.md) — Running-service verification, separate from unit and adapter tests. Metrics acceptance tests do not establish deployment-level network isolation; verify that against deployed services.
