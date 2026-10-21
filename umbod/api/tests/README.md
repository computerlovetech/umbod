# Backend tests

Run the complete backend suite with `uv run pytest tests -q` from `umbod/api`.

## Shared persistence fixtures

`conftest.py` installs test connector plugins and isolates the default connector-store path for each test. Isolation changes configuration only; it does not create a SQLite database or prepare the application schema.

Tests that need a prepared default SQLite database explicitly request `prepared_connector_store_database` and pass its returned `Path` into their persistence configuration. This fixture prepares a fresh database for each test and shuts down its runtime during teardown.

Tests with their own prepared runtime or database path continue using `persistence_runtime.py`. Tests entering an application lifespan rely on that application's readiness checks. Neither category needs a second database from the shared preparation fixture.

`test_persistence_fixtures.py` verifies lazy database creation, configuration isolation, schema readiness through store operations, and fresh database state between tests.

Running-service integration tests remain separate under `live_runtime_tests` and use the Kind runtime runner described in the repository instructions.
