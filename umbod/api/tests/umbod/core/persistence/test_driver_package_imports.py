import ast
import re
import subprocess
import sys
from pathlib import Path
import umbod.infrastructure as infrastructure
import umbod.core.connectors.downstream_mcp as downstream_mcp
from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.capabilities.descriptions.stores.service import ConnectorCapabilityDescriptionOverrideStoreService
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import create_capability_activation_store
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStoreService, ConnectorHealthStoreService
from umbod.core.connectors.openapi.stores import OpenApiConnectorStoreService
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.infrastructure.persistence.inmemory.database import InMemoryDatabase
from umbod.infrastructure.persistence.sqlite.compiler import CompiledStatement, SQLiteCompiler
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper

def test_downstream_mcp_package_exports_domain_and_application_interface() -> None:
    for name in downstream_mcp.__all__:
        assert hasattr(downstream_mcp, name)
    assert not any("FastMCP" in name for name in downstream_mcp.__all__)


def test_downstream_mcp_adapters_package_does_not_export_implementations() -> None:
    path = (
        Path(__file__).parents[4]
        / "src"
        / "umbod"
        / "core"
        / "connectors"
        / "downstream_mcp"
        / "adapters"
        / "__init__.py"
    )
    assert path.read_text() == ""


def test_downstream_mcp_core_contracts_do_not_import_fastmcp() -> None:
    root = (
        Path(__file__).parents[4]
        / "src"
        / "umbod"
        / "core"
        / "connectors"
        / "downstream_mcp"
    )
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if "adapters" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            if any(module == "fastmcp" or module.startswith("fastmcp.") for module in modules):
                violations.append(f"{path}:{node.lineno}")
    assert violations == []


def test_downstream_mcp_fastmcp_implementations_are_encapsulated() -> None:
    root = (
        Path(__file__).parents[4]
        / "src"
        / "umbod"
        / "core"
        / "connectors"
        / "downstream_mcp"
        / "adapters"
    )
    assert (root / "composition.py").exists()
    assert all((root / "fastmcp" / f"{name}.py").exists() for name in ("client", "connection", "discovery", "oauth", "probe"))
    assert all(not (root / f"{name}.py").exists() for name in ("client", "connection", "connections", "discovery", "oauth", "probe"))


def test_infrastructure_package_exports_public_kernel() -> None:
    for name in infrastructure.__all__:
        assert hasattr(infrastructure, name)

def test_infrastructure_public_surface_is_composition_only() -> None:
    assert set(infrastructure.__all__) == {
        'AppPersistenceRuntime',
        'ConfiguredPersistenceRuntimeProvider',
    }
    forbidden = {
        'InMemoryDatabase',
        'SQLiteDatabase',
        'SQLiteCompiler',
        'SQLiteValueMapper',
        'CompiledStatement',
        'prepare_application_schema',
        'SQLiteCurrentSchemaPreparation',
        'InMemoryPersistenceReadiness',
        'SQLitePersistenceReadiness',
        'InMemoryConnectorDefinitionStore',
        'SQLiteConnectorDefinitionStore',
        'create_downstream_mcp_stores',
        'create_group_permission_store',
        'DatabaseConnectorToolConfigurationMutationAdapter',
        'FastMCPDownstreamClientFactory',
    }
    assert forbidden.isdisjoint(set(infrastructure.__all__))

def test_external_modules_do_not_deep_import_infrastructure() -> None:
    source_root = Path(__file__).parents[4] / 'src' / 'umbod'
    tests_root = Path(__file__).parents[4] / 'tests'
    infra_src_root = source_root / 'infrastructure'
    infra_tests_root = tests_root / 'umbod' / 'infrastructure'
    violations: list[str] = []
    for root in (source_root, tests_root):
        for path in root.rglob('*.py'):
            try:
                path.relative_to(infra_src_root)
                continue
            except ValueError:
                pass
            try:
                path.relative_to(infra_tests_root)
                continue
            except ValueError:
                pass
            if path == Path(__file__):
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    if module.startswith('umbod.infrastructure.'):
                        violations.append(f'{path}:{node.lineno}:{module}')
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith('umbod.infrastructure.'):
                            violations.append(f'{path}:{node.lineno}:{alias.name}')
    assert violations == []

def test_messaging_composition_uses_runtime_database_without_sqlite_paths() -> None:
    source_root = Path(__file__).parents[4] / 'src' / 'umbod'
    paths = (source_root / 'rest' / 'factories.py', source_root / 'mcp' / 'messaging' / 'transport.py')
    violations: list[str] = []
    for path in paths:
        source = path.read_text()
        if 'SQLiteEvent' in source:
            violations.append(f'{path}:SQLiteEvent')
        if 'connector_store.sqlite_path' in source:
            violations.append(f'{path}:connector_store.sqlite_path')
    assert violations == []

def test_importing_core_persistence_does_not_load_aiosqlite() -> None:
    result = subprocess.run([sys.executable, '-c', "import sys; import umbod.core.persistence; raise SystemExit('aiosqlite' in sys.modules)"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_core_does_not_depend_on_infrastructure() -> None:
    core_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core'
    violations: list[str] = []
    for path in core_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('umbod.infrastructure'):
                violations.append(f'{path}:{node.lineno}')
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('umbod.infrastructure'):
                        violations.append(f'{path}:{node.lineno}')
    assert violations == []

def test_removed_persistence_compatibility_modules_are_absent() -> None:
    persistence_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'persistence'
    assert not (persistence_root / 'inmemory.py').exists()
    assert not (persistence_root / 'sqlite.py').exists()
    assert not (persistence_root / 'sqlite_compiler.py').exists()

def test_core_persistence_does_not_export_in_memory_database() -> None:
    import umbod.core.persistence as persistence
    assert 'InMemoryDatabase' not in persistence.__all__
    assert not hasattr(persistence, 'InMemoryDatabase')

def test_connector_event_wrappers_are_absent_from_core() -> None:
    core_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core'
    event_paths = (
        core_root / 'publishing' / 'events.py',
        core_root / 'invocation' / 'events.py',
        core_root / 'configuration' / 'events.py',
        core_root / 'activation' / 'events.py',
        core_root / 'capabilities' / 'descriptions' / 'events.py',
    )
    forbidden_names = {'InMemoryConnectorPublicationEventCheckpointStore', 'InMemoryConnectorPublicationEventStream', 'InMemoryConnectorRuntimeStateEventStream', 'InMemoryConnectorToolChangeEventCheckpointStore', 'InMemoryConnectorToolChangeEventStream'}
    defined_names: set[str] = set()
    for events_path in event_paths:
        tree = ast.parse(events_path.read_text(), filename=str(events_path))
        defined_names.update(node.name for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)))
    assert defined_names.isdisjoint(forbidden_names)

def test_core_has_no_thin_backend_named_store_aliases() -> None:
    core_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core'
    forbidden_names = {'InMemoryEncryptedConnectorConfigurationStore', 'SQLiteEncryptedConnectorConfigurationStore', 'InMemoryConnectorDefinitionStore', 'InMemoryConnectorHealthStore', 'SQLiteConnectorDefinitionStore', 'SQLiteConnectorHealthStore', 'InMemoryConnectorPublishingStore', 'SQLiteConnectorPublishingStore', 'SQLiteActivationStore', 'InMemoryOpenApiConnectorStore', 'SQLiteOpenApiConnectorStore', 'InMemoryGroupPermissionStore', 'SQLiteGroupPermissionStore', 'InMemoryConnectorCapabilityDescriptionOverrideStore', 'SQLiteConnectorCapabilityDescriptionOverrideStore'}
    violations: list[str] = []
    for path in core_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in forbidden_names:
                    violations.append(f'{path}:{node.lineno}:{node.name}')
    assert violations == []

def test_connector_publishing_core_package_only_imports_core_modules() -> None:
    publishing_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'publishing'
    violations: list[str] = []
    for path in publishing_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                imported_modules.append(node.module or '')
            elif isinstance(node, ast.Import):
                imported_modules.extend((alias.name for alias in node.names))
            for module in imported_modules:
                if module.startswith('umbod.') and (not module.startswith('umbod.core.')):
                    violations.append(f'{path}:{node.lineno}:{module}')
    assert violations == []

def test_domain_store_services_originate_in_core() -> None:
    assert ConnectorDefinitionStoreService.__module__.startswith('umbod.core.connectors.downstream_mcp.stores')
    assert ConnectorHealthStoreService.__module__.startswith('umbod.core.connectors.downstream_mcp.stores')
    assert ConnectorPublishingStoreService.__module__.startswith('umbod.core.publishing.stores')
    assert OpenApiConnectorStoreService.__module__.startswith('umbod.core.connectors.openapi.stores')
    assert GroupPermissionStoreService.__module__.startswith('umbod.core.permissions.stores')
    assert ConnectorCapabilityDescriptionOverrideStoreService.__module__.startswith('umbod.core.capabilities.descriptions')

def test_domain_store_factories_originate_in_core() -> None:
    assert create_group_permission_store.__module__ == 'umbod.core.permissions.factories'
    assert create_connector_publishing_store.__module__ == 'umbod.core.publishing.factories'
    assert create_encrypted_connector_configuration_store.__module__ == 'umbod.core.configuration.persistence.factories'
    assert create_capability_activation_store.__module__ == 'umbod.core.activation.factories'
    assert ConfiguredOpenApiConnectorStoreFactory.__module__ == 'umbod.core.connectors.openapi.stores.factories'
    assert ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory.__module__ == 'umbod.core.capabilities.descriptions.factories'

def test_downstream_connector_health_service_only_imports_core_modules() -> None:
    service_path = Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'connectors' / 'downstream_mcp' / 'stores' / 'health.py'
    tree = ast.parse(service_path.read_text(), filename=str(service_path))
    imported_modules = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all((not module.startswith('umbod.') or module.startswith('umbod.core.') for module in imported_modules))

def test_importing_connector_publishing_domain_does_not_load_infrastructure() -> None:
    result = subprocess.run([sys.executable, '-c', "import sys; import umbod.core.publishing; raise SystemExit(any(name.startswith('umbod.infrastructure') for name in sys.modules))"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_importing_connector_publishing_domain_does_not_load_aiosqlite() -> None:
    result = subprocess.run([sys.executable, '-c', "import sys; import umbod.core.publishing; raise SystemExit('aiosqlite' in sys.modules)"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def _assert_import_does_not_load_persistence_drivers(module_name: str) -> None:
    command = f"import importlib, sys; importlib.import_module({module_name!r}); loaded = [name for name in sys.modules if name == 'aiosqlite' or name.startswith('umbod.infrastructure')]; sys.exit(','.join(loaded)) if loaded else None"
    result = subprocess.run([sys.executable, '-c', command], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_importing_neutral_permission_modules_does_not_load_persistence_drivers() -> None:
    for module_name in ('umbod.core.permissions.domain', 'umbod.core.permissions.ports', 'umbod.core.permissions.stores.schema', 'umbod.core.permissions.stores.service'):
        _assert_import_does_not_load_persistence_drivers(module_name)

def test_importing_neutral_openapi_persistence_modules_does_not_load_drivers() -> None:
    for module_name in ('umbod.core.connectors.openapi.stores.schema', 'umbod.core.connectors.openapi.stores.service', 'umbod.core.connectors.openapi.stores'):
        _assert_import_does_not_load_persistence_drivers(module_name)

def test_importing_neutral_capability_override_modules_does_not_load_drivers() -> None:
    for module_name in ('umbod.core.capabilities.descriptions.overrides', 'umbod.core.capabilities.descriptions.stores.schema', 'umbod.core.capabilities.descriptions.stores.service'):
        _assert_import_does_not_load_persistence_drivers(module_name)

def test_driver_packages_export_adapter_types() -> None:
    assert InMemoryDatabase.__module__.startswith('umbod.infrastructure.persistence.inmemory')
    assert SQLiteDatabase.__module__.startswith('umbod.infrastructure.persistence.sqlite')
    assert SQLiteCompiler.__module__.startswith('umbod.infrastructure.persistence.sqlite')
    assert SQLiteValueMapper.__module__.startswith('umbod.infrastructure.persistence.sqlite')
    assert CompiledStatement.__module__.startswith('umbod.infrastructure.persistence.sqlite')

def test_infrastructure_has_no_domain_store_or_factory_packages() -> None:
    persistence_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'infrastructure' / 'persistence'

    def has_python(path: Path) -> bool:
        return path.exists() and any(path.rglob('*.py'))

    assert not has_python(persistence_root / 'factories')
    assert not has_python(persistence_root / 'inmemory' / 'stores')
    assert not has_python(persistence_root / 'sqlite' / 'stores')
    assert not (persistence_root / 'tool_configuration_mutation.py').exists()
    infra_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'infrastructure'
    assert not has_python(infra_root / 'downstream_mcp')

def test_permission_composition_has_no_sqlite_or_backend_config_dependencies() -> None:
    source_root = Path(__file__).parents[4] / 'src' / 'umbod'
    paths = (source_root / 'rest' / 'mcp_permissions' / 'dependencies.py', source_root / 'mcp' / 'openapi_connectors' / 'factories.py')
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and 'sqlite' in (node.module or '').lower():
                violations.append(f'{path}:{node.lineno}:{node.module}')
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if 'sqlite' in alias.name.lower():
                        violations.append(f'{path}:{node.lineno}:{alias.name}')
            if isinstance(node, ast.Attribute) and node.attr in {'connector_store', 'sqlite_path'}:
                violations.append(f'{path}:{node.lineno}:{node.attr}')
    assert violations == []

def test_store_factories_do_not_call_ensure_schema() -> None:
    source_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core'
    paths = (source_root / 'publishing' / 'factories.py', source_root / 'permissions' / 'factories.py', source_root / 'connectors' / 'downstream_mcp' / 'stores' / 'factory.py', source_root / 'configuration' / 'persistence' / 'factories.py', source_root / 'activation' / 'factories.py')
    violations: list[str] = []
    for path in paths:
        source = path.read_text()
        if 'ensure_schema' in source:
            violations.append(str(path))
    assert violations == []

def test_obsolete_persistence_compatibility_facades_are_absent() -> None:
    api_root = Path(__file__).parents[4]
    assert not (api_root / 'src' / 'umbod' / 'infrastructure' / 'persistence' / 'messaging.py').exists()
    assert not (api_root / 'src' / 'umbod' / 'infrastructure' / 'persistence' / 'messaging').exists()
    assert not (api_root / 'tests' / 'sqlite_openapi_store.py').exists()
    forbidden_names = {'DatabaseEventStreamFactory', 'DatabaseEventCheckpointStoreFactory', 'prepared_sqlite_openapi_store'}
    violations: list[str] = []
    for source_root in (api_root / 'src', api_root / 'tests'):
        for path in source_root.rglob('*.py'):
            source = path.read_text()
            for forbidden_name in forbidden_names:
                if forbidden_name in source and path != Path(__file__):
                    violations.append(f'{path}:{forbidden_name}')
    assert violations == []

def test_messaging_package_does_not_import_umbod() -> None:
    messaging_root = Path(__file__).parents[4] / 'src' / 'messaging'
    violations: list[str] = []
    for path in messaging_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('umbod'):
                violations.append(f'{path}:{node.lineno}:{node.module}')
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('umbod'):
                        violations.append(f'{path}:{node.lineno}:{alias.name}')
    assert violations == []
    assert not (messaging_root / 'persistence.py').exists()

def test_database_messaging_stores_live_in_core() -> None:
    api_root = Path(__file__).parents[4]
    core_messaging = api_root / 'src' / 'umbod' / 'core' / 'messaging'
    assert (core_messaging / '__init__.py').exists()
    assert (core_messaging / 'stores' / 'event_stream.py').exists()
    assert (core_messaging / 'stores' / 'checkpoints.py').exists()
    assert (core_messaging / 'stores' / 'schema.py').exists()
    forbidden = {
        'CHECKPOINT_TABLE',
        'DatabaseEventCheckpointStore',
        'DatabaseEventStream',
        'EVENT_TABLE',
    }
    assert forbidden.isdisjoint(set(infrastructure.__all__))


def test_sqlite_readiness_uses_current_schema_preparation_and_schema_inventory() -> None:
    api_root = Path(__file__).parents[4]
    persistence_root = api_root / 'src' / 'umbod' / 'infrastructure' / 'persistence'
    runtime_source = (persistence_root / 'runtime.py').read_text()
    schema_source = (persistence_root / 'schema_preparation.py').read_text()
    sqlite_schema_source = (persistence_root / 'sqlite' / 'schema_preparation.py').read_text()
    assert 'SQLiteCurrentSchemaPreparation(self._database).execute()' in runtime_source
    assert 'APPLICATION_PERSISTENCE_TABLES' in schema_source
    assert 'LEGACY_CATALOG_TABLE' not in schema_source
    assert 'APPLICATION_PERSISTENCE_TABLES' in sqlite_schema_source
    assert not (persistence_root / 'sqlite' / 'migrations').exists()
    assert not (persistence_root / 'sqlite' / 'persistence_plan.py').exists()

def test_downstream_mcp_factory_has_no_database_path() -> None:
    source = (Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'connectors' / 'downstream_mcp' / 'stores' / 'factory.py').read_text()
    assert 'database_path' not in source
    assert 'sqlite_path' not in source

def test_only_mcp_top_level_loader_constructs_persistence_runtime() -> None:
    mcp_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'mcp'
    violations: list[str] = []
    for path in mcp_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called_name = ''
            if isinstance(node.func, ast.Name):
                called_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                called_name = node.func.attr
            if called_name not in {'ConfiguredPersistenceRuntimeProvider', 'SQLiteDatabase', 'InMemoryDatabase'}:
                continue
            enclosing_functions = [candidate for candidate in ast.walk(tree) if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in ast.walk(candidate)]
            allowed = path.name == 'public_app.py' and any((function.name == 'load_configured_public_app_config' for function in enclosing_functions)) and (called_name == 'ConfiguredPersistenceRuntimeProvider')
            if not allowed:
                violations.append(f'{path}:{node.lineno}:{called_name}')
    assert violations == []

def test_nested_mcp_composition_does_not_inspect_persistence_backend_config() -> None:
    mcp_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'mcp'
    violations: list[str] = []
    for path in mcp_root.rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in {'sqlite_path', 'connector_store', 'type'}:
                continue
            if path.name == 'public_app.py' and node.attr == 'connector_store':
                enclosing_functions = [candidate for candidate in ast.walk(tree) if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and candidate.name == 'load_configured_public_app_config' and (node in ast.walk(candidate))]
                if enclosing_functions:
                    continue
            if node.attr != 'type':
                violations.append(f'{path}:{node.lineno}:{node.attr}')
    assert violations == []

def test_mcp_public_app_has_no_connector_store_type_branching() -> None:
    source = (Path(__file__).parents[4] / 'src' / 'umbod' / 'mcp' / 'public_app.py').read_text()
    assert 'connector_store.type == "sqlite"' not in source
    assert 'connector_store.type' not in source

def test_downstream_mcp_composition_has_no_application_or_backend_awareness() -> None:
    path = Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'connectors' / 'downstream_mcp' / 'stores' / 'factory.py'
    source = path.read_text()
    forbidden_names = {'AppConfig', 'PersistenceConfig', 'connector_store', 'sqlite_path', 'database_path', 'SQLiteDatabase', 'InMemoryDatabase', 'ConfiguredPersistenceRuntimeProvider'}
    assert all((name not in source for name in forbidden_names))

def test_core_persistence_is_backend_and_driver_neutral() -> None:
    persistence_root = Path(__file__).parents[4] / 'src' / 'umbod' / 'core' / 'persistence'
    backend_tokens = re.compile('\\b(sqlite|postgres(?:ql)?|aiosqlite|psycopg)\\b', re.IGNORECASE)
    sql_syntax = re.compile('\\b(SELECT\\s+.+\\s+FROM|INSERT\\s+INTO|UPDATE\\s+.+\\s+SET|DELETE\\s+FROM|CREATE\\s+TABLE|DROP\\s+TABLE|ALTER\\s+TABLE|ON\\s+CONFLICT|PRIMARY\\s+KEY)\\b', re.IGNORECASE)
    boundary_names = {'path', 'database_path', 'connection', 'connection_string', 'cursor', 'driver', 'execute', 'executemany', 'commit', 'rollback'}
    violations: list[str] = []
    for path in persistence_root.rglob('*.py'):
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if module.startswith('umbod.infrastructure'):
                    violations.append(f'{path}:{node.lineno}:infrastructure import')
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('umbod.infrastructure'):
                        violations.append(f'{path}:{node.lineno}:infrastructure import')
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if backend_tokens.search(node.value):
                    violations.append(f'{path}:{node.lineno}:backend or driver name')
                if sql_syntax.search(node.value):
                    violations.append(f'{path}:{node.lineno}:SQL syntax')
            if isinstance(node, (ast.Name, ast.Attribute, ast.arg)):
                identifier = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else node.arg
                if identifier.lower() in boundary_names:
                    violations.append(f'{path}:{node.lineno}:adapter boundary concept {identifier}')
    assert violations == []
