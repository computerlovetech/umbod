from pathlib import Path

import pytest

from tests.support.sqlite_boundaries import scan_sqlite_boundaries


BUSINESS_PATH = "umbod/core/test_service.py"
CONFIG_PATH = "umbod/config/test_settings.py"
HOST_PATH = "umbod/hosting/integration/test_api_server_process.py"


def test_api_business_tests_do_not_depend_on_sqlite() -> None:
    root = Path(__file__).resolve().parents[2]
    violations = tuple(
        violation
        for path in sorted(root.rglob("*.py"))
        for violation in scan_sqlite_boundaries(path.read_text(), path.relative_to(root).as_posix())
    )
    assert not violations, "\n".join(
        f"{item.path}:{item.line}: {item.reason}" for item in violations
    )


@pytest.mark.parametrize(
    "source,path,reason",
    [
        ("import sqlite3 as sql", BUSINESS_PATH, "backend import"),
        ("from textwrap import dedent; program = dedent('import sqlite3; sqlite3.connect(\"db\")')", BUSINESS_PATH, "embedded Python"),
        ("from textwrap import dedent as clean; program = clean('import sqlite3')", BUSINESS_PATH, "embedded Python"),
        ("TelemetryAnalyticsConfig.model_validate(obj={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("analytics = TelemetryAnalyticsConfig(); analytics.model_copy(update={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("analytics: TelemetryAnalyticsConfig = TelemetryAnalyticsConfig(); analytics.model_copy(update={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("settings.telemetry_analytics.model_copy(update={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("settings.telemetry_analytics.enabled = True", BUSINESS_PATH, "configuration mutation"),
        ("settings.connector_store.type = 'sqlite'", BUSINESS_PATH, "configuration mutation"),
        ("import aiosqlite as sql; sql.connect('database')", BUSINESS_PATH, "factory or connection"),
        ("from persistence_runtime import create_sqlite_runtime as make; make('db')", BUSINESS_PATH, "factory or connection"),
        ("import persistence_runtime as runtime; runtime.prepared_sqlite_runtime('db')", BUSINESS_PATH, "factory or connection"),
        ("from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase as DB; DB('db')", BUSINESS_PATH, "factory or connection"),
        ("from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver as Driver; Driver('db')", BUSINESS_PATH, "factory or connection"),
        ("import sqlite3; connect = sqlite3.connect; connect('db')", BUSINESS_PATH, "factory or connection"),
        ("import importlib; importlib.import_module('aiosqlite')", BUSINESS_PATH, "dynamic backend import"),
        ("from tests.umbod.infrastructure.persistence.adapters import DATABASE_ADAPTERS as adapters", BUSINESS_PATH, "registry import"),
        ("from helpers import DATABASE_ADAPTERS", BUSINESS_PATH, "registry import"),
        ("SQLiteConnectorStoreConfig(sqlite_path='db')", BUSINESS_PATH, "connector configuration"),
        ("ConnectorStoreConfig(type='sqlite')", BUSINESS_PATH, "connector configuration"),
        ("from config import SQLiteConnectorStoreConfig as Store; Store()", BUSINESS_PATH, "connector configuration"),
        ("AppConfig.model_validate({'connector_store': {'type': 'sqlite'}})", BUSINESS_PATH, "configuration payload"),
        ("TelemetryAnalyticsConfig(enabled=True)", BUSINESS_PATH, "analytics configuration"),
        ("AppConfig.model_validate({'telemetry_analytics': {'enabled': True}})", BUSINESS_PATH, "analytics configuration"),
        ("AppConfig(telemetry_analytics={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("TelemetryAnalyticsConfig.model_validate({'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("TelemetryAnalyticsConfig.model_copy(update={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("TelemetryAnalyticsConfig.model_construct(enabled=True)", BUSINESS_PATH, "analytics configuration"),
        ("from config import TelemetryAnalyticsConfig as Analytics; Analytics.model_validate({'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("import umbod.config as cfg; cfg.TelemetryAnalyticsConfig.model_copy(update={'enabled': True})", BUSINESS_PATH, "analytics configuration"),
        ("from config import ConnectorStoreConfig as Store; Store.model_validate({'type': 'sqlite'})", BUSINESS_PATH, "connector configuration"),
        ("AppConfig.model_validate({'telemetry': {'analytics': {'enabled': True}}})", BUSINESS_PATH, "analytics configuration payload"),
        ("AppConfig(sqlite_path='db')", BUSINESS_PATH, "path configuration"),
        ("settings.connector_store.sqlite_path", BUSINESS_PATH, "path reference"),
        ("import os; os.environ['UMBOD_CONNECTOR_STORE'] = 'sqlite'", BUSINESS_PATH, "connector environment"),
        ("monkeypatch.setenv('UMBOD_TELEMETRY_ANALYTICS_ENABLED', 'True')", BUSINESS_PATH, "analytics environment"),
        ("_config(monkeypatch, UMBOD_CONNECTOR_STORE='sqlite')", BUSINESS_PATH, "connector environment"),
        ("_config(monkeypatch, UMBOD_TELEMETRY_ANALYTICS_ENABLED='1')", BUSINESS_PATH, "analytics environment"),
        ("import os; monkeypatch.setitem(os.environ, 'UMBOD_CONNECTOR_STORE', 'sqlite')", BUSINESS_PATH, "connector environment"),
        ("env = {'UMBOD_TELEMETRY_ANALYTICS_ENABLED': '1'}", BUSINESS_PATH, "analytics environment"),
        ("env = {'UMBOD_CONNECTOR_STORE_SQLITE_PATH': 'unused'}", BUSINESS_PATH, "path environment"),
        ("def test_service(prepared_connector_store_database): pass", BUSINESS_PATH, "physical connector database fixture"),
        ("async def test_service(*, isolated_connector_store_database): pass", BUSINESS_PATH, "physical connector database fixture"),
        ("program = 'import sqlite3; sqlite3.connect(\"db\")'", BUSINESS_PATH, "embedded Python"),
        ("program = textwrap.dedent('    import sqlite3\\n    sqlite3.connect(\"db\")')", BUSINESS_PATH, "embedded Python"),
        ("program = f'import sqlite3; sqlite3.connect({path!r})'", BUSINESS_PATH, "embedded Python"),
        ("import subprocess; subprocess.run(['python', '-c', 'import sqlite3'])", BUSINESS_PATH, "embedded Python"),
        ("from subprocess import run as launch; launch(['python', '-c', 'import sqlite3'])", BUSINESS_PATH, "embedded Python"),
        ("import subprocess; command = 'import sqlite3'; subprocess.run(['python', '-c', command])", BUSINESS_PATH, "embedded Python"),
        ("import sqlite3", "umbod/rest/test_not_sqlite.py", "backend import"),
        ("import sqlite3", "umbod/hosting/integration/test_other_process.py", "backend import"),
        ("import sqlite3", CONFIG_PATH, "backend import"),
        ("create_sqlite_runtime('db')", CONFIG_PATH, "factory or connection"),
        ("ConfiguredPersistenceRuntimeProvider(config)", CONFIG_PATH, "must not construct persistence runtimes"),
        ("from runtime import create_configured_analytics_runtime as make; make(config)", CONFIG_PATH, "must not construct persistence runtimes"),
        ("import sqlite3; sqlite3.connect('db')", "conftest.py", "backend import"),
        ("SQLiteDatabase('db')", "umbod/core/persistence/test_driver_package_imports.py", "factory or connection"),
        ("create_sqlite_runtime('db')", "support/innocent.py", "factory or connection"),
    ],
)
def test_sqlite_boundary_rejects_physical_business_dependencies(source: str, path: str, reason: str) -> None:
    violations = scan_sqlite_boundaries(source, path)
    assert any(reason in item.reason for item in violations)
    assert all(item.path == path and item.line >= 1 for item in violations)


@pytest.mark.parametrize(
    "source,path",
    [
        ("AppConfig.model_validate({'connector_store': {'type': 'memory'}})", BUSINESS_PATH),
        ("TelemetryAnalyticsConfig(enabled=False)", BUSINESS_PATH),
        ("from textwrap import dedent; program = dedent('value = 1')", BUSINESS_PATH),
        ("TelemetryAnalyticsConfig.model_validate(obj={'enabled': False})", BUSINESS_PATH),
        ("analytics = TelemetryAnalyticsConfig(); analytics.model_copy(update={'enabled': False})", BUSINESS_PATH),
        ("settings.telemetry_analytics.enabled = False; settings.connector_store.type = 'inmemory'", BUSINESS_PATH),
        ("AppConfig.model_validate({'telemetry_analytics': {'enabled': False}})", BUSINESS_PATH),
        ("AppConfig(telemetry_analytics={'enabled': False})", BUSINESS_PATH),
        ("TelemetryAnalyticsConfig.model_validate({'enabled': False})", BUSINESS_PATH),
        ("TelemetryAnalyticsConfig.model_copy(update={'enabled': False})", BUSINESS_PATH),
        ("TelemetryAnalyticsConfig.model_construct(enabled=False)", BUSINESS_PATH),
        ("_config(monkeypatch, UMBOD_CONNECTOR_STORE='memory', UMBOD_TELEMETRY_ANALYTICS_ENABLED='false')", BUSINESS_PATH),
        ("ConfiguredPersistenceRuntimeProvider(memory_config)", BUSINESS_PATH),
        ("create_configured_analytics_runtime(memory_config)", BUSINESS_PATH),
        ("query = Query(field='sqlite'); negative_path = 'missing.sqlite'", BUSINESS_PATH),
        ("from umbod.mcp.connectors.native import SQLiteConnectorRuntimeStateReader; SQLiteConnectorRuntimeStateReader(registry, store, publications)", BUSINESS_PATH),
        ("cases = ['import sqlite3', 'SQLiteDatabase()']", BUSINESS_PATH),
        ("assert settings.connector_store.type == 'sqlite'", CONFIG_PATH),
        ("SQLiteConnectorStoreConfig(sqlite_path='db')", CONFIG_PATH),
        ("AppConfig.model_validate({'connector_store': {'type': 'sqlite'}})", CONFIG_PATH),
        ("TelemetryAnalyticsConfig(enabled=True)", CONFIG_PATH),
        ("TelemetryAnalyticsConfig.model_copy(update={'enabled': True})", CONFIG_PATH),
        ("AppConfig.model_validate({'telemetry_analytics': {'enabled': True}})", CONFIG_PATH),
        ("path.touch(); path.hardlink_to(other)", CONFIG_PATH),
        ("import sqlite3; sqlite3.connect('db')", HOST_PATH),
        ("program = 'import sqlite3'; env = {'UMBOD_CONNECTOR_STORE': 'sqlite'}", HOST_PATH),
        ("import sqlite3; sqlite3.connect('db')", "umbod/infrastructure/persistence/test_driver.py"),
        ("import sqlite3; sqlite3.connect('db')", "persistence_runtime.py"),
        ("import sqlite3; sqlite3.connect('db')", "support/persistence_processes.py"),
        ("from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase", "umbod/core/persistence/test_driver_package_imports.py"),
        ("import importlib; importlib.import_module('aiosqlite')", "umbod/core/persistence/test_driver_package_imports.py"),
    ],
)
def test_sqlite_boundary_allows_memory_and_explicit_physical_owners(source: str, path: str) -> None:
    assert scan_sqlite_boundaries(source, path) == ()
