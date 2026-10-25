# Backend tests

Run the complete backend suite with `uv run --locked pytest tests -q -n auto --maxprocesses=4 --dist=worksteal` from `umbod/api`.

## Parallel execution

The development dependency `pytest-xdist` distributes tests across separate worker processes. Automatic worker selection is capped at four; work stealing balances tests with different durations. The MCP and API subsets use the same options with `-k mcp` or `-k "not mcp"`.

Use `-n 0` instead of the parallel options for serial execution, debugger sessions, or small focused selections where worker startup costs more than it saves. `-n 2 --dist=worksteal` provides a lower-resource parallel option. Do not launch concurrent full-suite runs or use uncapped worker selection.

Parallelism is enabled explicitly by the backend command and CI, not global pytest configuration. Kind/live-runtime integration tests remain serial. New tests must collect deterministically and isolate writable files, databases, and network listeners across processes.

## Shared persistence fixtures

`conftest.py` installs test connector plugins and isolates the default connector-store path for each test. Isolation changes configuration only; it does not create a SQLite database or prepare the application schema.

Tests that need a prepared default SQLite database explicitly request `prepared_connector_store_database` and pass its returned `Path` into their persistence configuration. This fixture prepares a fresh database for each test and shuts down its runtime during teardown.

Tests with their own prepared runtime or database path continue using `persistence_runtime.py`. Tests entering an application lifespan rely on that application's readiness checks. Neither category needs a second database from the shared preparation fixture.

`test_persistence_fixtures.py` verifies lazy database creation, configuration isolation, schema readiness through store operations, and fresh database state between tests.

## Metrics listeners

Tests unrelated to the metrics HTTP endpoint explicitly disable `rest.metrics_enabled` or `mcp.metrics_enabled` in their application settings. This avoids real listener startup, shutdown delays, and shared-port conflicts while preserving application lifespan, persistence readiness, and metric recording.

`mcp_fixtures.py` disables the MCP metrics listener on a copied configuration, leaving caller settings unchanged. Dedicated metrics HTTP-server tests retain real network lifecycle coverage. Their actual servers bind port zero and keep ownership of the assigned sockets; tests observe the bound address and assert listener shutdown instead of reserving and releasing a supposedly free port. The MCP health and administrator invocation tests verify that listener-free applications remain usable and continue recording invocation metrics; REST lifecycle tests cover the corresponding disabled-listener contract.

`umbod/rest/test_prometheus_rest_api_metrics_acceptance.py` sends real HTTP requests through the REST metrics middleware and scrapes the production Prometheus endpoint. `umbod/mcp/test_prometheus_mcp_metrics_acceptance.py` records completed invocations through the recorder port and scrapes the production MCP metrics endpoint, with separate in-memory aggregation and reset checks. These tests do not simulate network accessibility, endpoint configuration, platform samples, or process restarts. Recorder, authentication, application composition, and listener lifecycle checks remain in their dedicated modules; deployment-level network isolation requires deployment and running-service verification.

## Virtual filesystem acceptance

`umbod/core/virtual_filesystem/` contains the initial standalone core acceptance slice for root discovery, nested creation, and streamed write/read. Its domain language, direct-Python driver, composition factory, and in-memory dependency doubles live in `support/virtual_filesystem/`. These tests target the public production service, not a simulated service. The production VFS module is not yet implemented, so the expected initial result is missing-SUT setup failures after successful collection.

The scenario mapping and explicit deferrals are recorded in `.atdd/features/virtual-filesystem/04-acceptance-test-plan.md` at the repository root. This initial slice does not establish full feature coverage or conformance of future storage adapters.

## Contract and architecture checks

Store contracts retain both in-memory and SQLite cases. Only SQLite-specific factories prepare SQLite schemas. Persistence composition checks write through one store bundle and read through independent bundles, including a separately opened database, rather than inspecting private database fields. HTTP header policy tests define independent expected policies and exercise the transport port.

`umbod/core/persistence/test_driver_package_imports.py` lazily caches source text and parsed syntax trees within each worker process. Rules inspect these trees without modifying them and retain independent diagnostics. Fresh-process import checks remain uncached.

Running-service integration tests remain separate under `live_runtime_tests` and use the Kind runtime runner described in the repository instructions.
