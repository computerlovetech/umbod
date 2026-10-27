# Backend tests

Run the complete backend suite with `uv run --locked pytest tests -q -n auto --maxprocesses=4 --dist=worksteal` from `umbod/api`.

## Parallel execution

The development dependency `pytest-xdist` distributes tests across separate worker processes. Automatic worker selection is capped at four; work stealing balances tests with different durations. The MCP and API subsets use the same options with `-k mcp` or `-k "not mcp"`.

Use `-n 0` instead of the parallel options for serial execution, debugger sessions, or small focused selections where worker startup costs more than it saves. `-n 2 --dist=worksteal` provides a lower-resource parallel option. Do not launch concurrent full-suite runs or use uncapped worker selection.

Parallelism is enabled explicitly by the backend command and CI, not global pytest configuration. Kind/live-runtime integration tests remain serial. New tests must collect deterministically and isolate writable files, databases, and network listeners across processes.

## Deferred read planning

`umbod/core/persistence/test_read_plan.py` checks deferred registration, exact-read deduplication, result ownership, lifecycle and fresh execution against both database ports. `umbod/core/user_catalogue/test_read_state.py` checks bounded state batches, complete activation identities, missing facts and revocation. `umbod/rest/user_catalogue/test_catalogue_query_budget.py` checks constant reads and sessions for one versus forty shared tools and next-request grant revocation. Its counting adapters observe neutral persistence calls, not SQL text. `umbod/infrastructure/persistence/test_planned_activation_reads.py` separately verifies SQLite uses the existing compound index. `umbod/core/openapi_connectors/test_bulk_operation_reads.py` checks current-catalogue operation isolation and constant operation-read budgets.

## Request-local caching

`umbod/core/caching/` tests the public `AsyncRequestCache` protocol for successful and empty-result reuse, separate keys and instances, concurrent load sharing, failure retry, same-task recursion, cancellation, and invalidation while older loads are still running. Event-controlled loaders and drivers coordinate concurrency without fixed sleeps. `test_cache_driver.py` covers injected storage, shared-driver namespace isolation, suspended driver lookups/writes, failures, cancellation and generation-safe invalidation. `umbod/infrastructure/key_value/` verifies the in-memory driver through `KeyValueDriver`, including explicit misses, false values, compound keys, overwrites, deletion, scoped clearing and fresh composition. Core wrapper tests under `umbod/core/capabilities/` and `umbod/core/publishing/` cover publication reuse, complete catalogue indexing, failure retry and nested schema-copy isolation. `umbod/rest/mcp_permissions/test_assignable_permission_request_cache.py` verifies the opt-in GET dependency, reduced query budgets on both persistence backends, next-request freshness and uncached mutations. Database sessions and deferred read plans remain unchanged.

## Shared persistence fixtures

`conftest.py` installs test connector plugins and isolates the default connector-store path for each test. Isolation changes configuration only; it does not create a SQLite database or prepare the application schema.

Tests that need a prepared default SQLite database explicitly request `prepared_connector_store_database` and pass its returned `Path` into their persistence configuration. This fixture prepares a fresh database for each test and shuts down its runtime during teardown.

Tests with their own prepared runtime or database path continue using `persistence_runtime.py`. Tests entering an application lifespan rely on that application's readiness checks. Neither category needs a second database from the shared preparation fixture.

`test_persistence_fixtures.py` verifies lazy database creation, configuration isolation, schema readiness through store operations, and fresh database state between tests.

## Metrics listeners

Tests unrelated to the metrics HTTP endpoint explicitly disable `rest.metrics_enabled` or `mcp.metrics_enabled` in their application settings. This avoids real listener startup, shutdown delays, and shared-port conflicts while preserving application lifespan, persistence readiness, and metric recording.

`mcp_fixtures.py` disables the MCP metrics listener on a copied configuration, leaving caller settings unchanged. Dedicated metrics HTTP-server tests retain real network lifecycle coverage. Their actual servers bind port zero and keep ownership of the assigned sockets; tests observe the bound address and assert listener shutdown instead of reserving and releasing a supposedly free port. The MCP health and administrator invocation tests verify that listener-free applications remain usable and continue recording invocation metrics; REST lifecycle tests cover the corresponding disabled-listener contract.

`umbod/rest/test_prometheus_rest_api_metrics_acceptance.py` sends real HTTP requests through the REST metrics middleware and scrapes the production Prometheus endpoint. `umbod/mcp/test_prometheus_mcp_metrics_acceptance.py` records completed invocations through the recorder port and scrapes the production MCP metrics endpoint, with separate in-memory aggregation and reset checks. These tests do not simulate network accessibility, endpoint configuration, platform samples, or process restarts. Recorder, authentication, application composition, and listener lifecycle checks remain in their dedicated modules; deployment-level network isolation requires deployment and running-service verification.

## Filesystem acceptance

`umbod/core/filesystem/` runs acceptance and namespace/content contracts over database-neutral namespace storage using existing in-memory and SQLite persistence runtimes, with independently parameterized in-memory/local content storage. `test_access_control.py` covers ownership/grant persistence through AccessControlDriver; `test_database_persistence.py` covers readiness, reopening, shared-database preservation, concurrent namespace writes, transaction failure, and independent processes. The domain language, direct-Python driver, composition factory, public-call recorder, and process helper live in `support/filesystem/`; there is no parallel fake filesystem. `umbod/infrastructure/filesystem/` retains concrete local-content symlink/cancellation checks and configured composition coverage, including rejection of retired namespace selectors. SQLite-specific checks exercise real task cancellation while awaiting the writer lock and after mutation before commit, plus nonblocking initialized reads while a shared database writer is active. The JSON namespace driver and its lock/snapshot tests are removed, not emulated in test support. ADR-006 checks retain exact infrastructure exports, prevent core/deep-driver imports, and verify lazy concrete content loading.

The original scenario mapping is recorded in `.atdd/features/filesystem/04-acceptance-test-plan.md` at the repository root. `.atdd/features/filesystem/10-database-namespace-and-policies.md` records the database/ownership scope and current verification. Ownership assignment remains separate from node creation; P08's move-dependent assertions remain deferred. These tests do not establish full feature coverage, authorization enforcement, combined node/owner transactions, JSON migration, or conformance of future storage backends.

## Contract and architecture checks

Store contracts retain both in-memory and SQLite cases. Only SQLite-specific factories prepare SQLite schemas. Persistence composition checks write through one store bundle and read through independent bundles, including a separately opened database, rather than inspecting private database fields. HTTP header policy tests define independent expected policies and exercise the transport port.

`umbod/core/persistence/test_driver_package_imports.py` lazily caches source text and parsed syntax trees within each worker process. Rules inspect these trees without modifying them and retain independent diagnostics. Fresh-process import checks remain uncached.

Running-service integration tests remain separate under `live_runtime_tests` and use the Kind runtime runner described in the repository instructions.
