import asyncio
import logging
import random
import secrets
import time

from umbod.core.connectors.downstream_mcp.adapters.composition import create_downstream_mcp_discovery, create_downstream_mcp_probe
from umbod.mcp.connectors.downstream_mcp.ports import DownstreamClientFactory
from umbod.mcp.runtime_adapters import OpenApiRuntimeAdapters, create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.factory import create_personal_mcp_transport
from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime, PersonalToolRuntime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.infrastructure import PersonalDiscoveryPreparation
from umbod.mcp.connectors.downstream_mcp.personal_discovery import PersonalDiscoveryOperations
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, McpPersonalToolRuntime, PersonalDiscoveryMiddleware, PersonalToolReservationMiddleware, personal_tool_permission_check

from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.publishing.factories import ConfiguredConnectorPublishingStoreFactory
from umbod.core.activation.factories import create_capability_activation_store
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.administrator.connector_configuration import AdministratorConnectorConfigurationService
from umbod.core.administrator.connector_configuration.reader import CatalogAdministratorConnectorConfigurationReader
from umbod.mcp.administrator.catalog import AdministratorConfigurationCatalog
from umbod.core.administrator.connector_configuration.mutation import CatalogAdministratorConfigurationMutation
from umbod.infrastructure import ContentConfig, ConfiguredPersistenceRuntimeProvider, create_content_driver

from collections.abc import AsyncIterator
from dataclasses import dataclass
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from typing import Literal
from fastmcp import FastMCP
from pydantic import TypeAdapter
from fastmcp.server.middleware import AuthMiddleware, Middleware
from mcp.server.request_state import RequestStateSecurity
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send
from umbod.core.connectors.native.bootstrap import DefaultConnectorRuntimeFactory
from umbod.core.invocation import ConnectorInvocationPolicy, StoredConnectorInvocationPolicy
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, InMemoryConnectorRegistry
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoveryStores as DownstreamRuntimeStores, DownstreamDiscoveryUnavailable, create_downstream_discovery_runtime
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.capabilities.tools.names import PublicToolIdentity
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod_sdk.connectors.discovery import load_connector_plugins
from umbod.mcp.agent_instructions import register_agent_instructions
from umbod.mcp.administrator import register_administrator_connector_configuration_tools
from umbod.mcp.auth import MCPAuthProviderFactory
from umbod.mcp.auth.consent_screen import install_umbod_consent_screen
from umbod.mcp.auth.factory import MCPAuthProvider
from umbod.mcp.auth.debug_middleware import MCPAuthDebugMiddleware
from umbod.mcp.context import ConnectorRuntimeStateSynchronizerOptions, PublicAppConfig, PublicAppRuntimeContext
from umbod.core.invocation import DatabaseApprovalNonceStore
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.mcp.connectors.native import (
    APPROVAL_TTL_SECONDS,
    ApprovalStateCodec,
    ConnectorRuntimeStateSynchronizer,
    CurrentInvocationApprovalCallerCapture,
    HttpConnectorRuntimeStateReader,
    HttpConnectorRuntimeStateSynchronizationSource,
    LocalConnectorRuntimeStateSynchronizationSource,
    McpConnectorInvocationApprovalPolicy,
    StoreBackedConnectorRuntimeStateReader,
    StoreBackedConnectorRuntimeStateSynchronizationSource,
    random_approval_token,
)
from umbod.mcp.connectors.native.prompts import ConnectorPromptRegistrationOptions, register_connector_prompts
from umbod.mcp.connectors.native.resources import ConnectorResourceRegistrationOptions, register_connector_resources
from umbod.mcp.connectors.native.tools import (
    ConnectorToolRuntimeStateSynchronizer,
    HttpConnectorToolRuntimeStateReader,
    InMemoryConnectorToolRuntimeStateStore,
    install_tool_list_changed_notifier,
    register_connector_tools,
)
from umbod.mcp.telemetry import McpTelemetryDependencies
from umbod.mcp.telemetry.composition import create_configured_mcp_telemetry
from umbod.mcp.logging import McpAuditIdentityAdapter
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import McpInvocationPublisher, McpSignals, McpToolExecutionPipelineFactory, SignalToolExecutionPipelineFactory
from umbod.mcp.connectors.downstream_mcp.inventory import shared_tool_inventory
from umbod.mcp.middleware import McpAuditMiddleware
from umbod.mcp.middleware.protocol_metrics import McpProtocolMetricsMiddleware
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, DatabaseFilesystemServiceFactory, RuntimeFilesystemGroupClaimFields, StaticFilesystemGroupClaimFields, register_filesystem_tools
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.mcp.connectors.downstream_mcp.coordinator import DownstreamDiscoveryAdapters, DownstreamDiscoveryCoordinator, DownstreamDiscoveryCoordinatorOptions, DownstreamDiscoveryStores, create_downstream_discovery_coordinator
from umbod.mcp.connectors.downstream_mcp import ConnectorAwareDownstreamMcpToolProvider, GroupDownstreamToolPermissionPolicy, NativeCapabilityProviderView, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.live_permission_updates import DatabaseGroupPermissionReader, GroupPermissionStateReloader, HttpGroupPermissionReader, RuntimeGroupPermissionSynchronizer
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.authorization import connector_tool_permission_check
from umbod.mcp.connectors.openapi import DatabaseGroupPermissionReaderFactory, build_openapi_codemode_executor
from umbod.mcp.connectors.openapi.inventory import read_openapi_tool_inventory
from umbod.mcp.connectors.openapi.discovery_runtime import initialize_openapi_discovery, reconcile_openapi_discovery
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, ConnectorStorePair, HttpConnectorRuntimeStateSourceStrategy, LocalConnectorRuntimeStateSourceStrategy, StoreBackedConnectorRuntimeStateSourceStrategy, resolve_connector_runtime_state_source_strategy
from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.config import AppConfig, InMemoryConnectorStoreConfig, SQLiteConnectorStoreConfig, load_server_app_config
from umbod.logging import flush_logging
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.messaging import McpMessagingAdapterFactory, RuntimeProjectionHealth, RuntimeProjectionSynchronizer
_CORS_HEADERS = {'Access-Control-Allow-Origin': '*'}
_MCP_HTTP_PATH = '/mcp'
_HEALTH_ROUTE = '/system/health'
_LOGO_ROUTE = '/assets/logo.png'
_LOGO_FILE = Path(__file__).resolve().parent / 'assets' / 'logo.png'
_INITIAL_RUNTIME_STATE_SYNC_TIMEOUT_SECONDS = 60.0
logger = logging.getLogger(__name__)
RuntimeStateArgument = InMemoryConnectorToolRuntimeStateStore | InMemoryGroupConnectorToolPermissions | None
RuntimeStateStores = tuple[InMemoryConnectorToolRuntimeStateStore | None, InMemoryGroupConnectorToolPermissions | None]
OpenApiCodemodeDiscoveryExposureMode = Literal['codemode']
OPENAPI_CODEMODE_DISCOVERY_EXPOSURE_MODES: frozenset[OpenApiCodemodeDiscoveryExposureMode] = frozenset({'codemode'})

async def build_mcp(settings: MCPAppSettings, auth_provider: MCPAuthProvider | None, runtime: ConnectorRuntime, persistence_runtime: PersistenceRuntime, *runtime_state: RuntimeStateArgument) -> FastMCP:
    downstream_client_factory = await create_configured_downstream_client_factory(settings, persistence_runtime.database)
    return await build_mcp_with_openapi_adapters(settings, auth_provider, runtime, runtime_state, create_configured_openapi_runtime_adapters(settings), persistence_runtime, telemetry=create_configured_mcp_telemetry(settings), downstream_client_factory=downstream_client_factory)

async def build_mcp_with_openapi_adapters(settings: MCPAppSettings, auth_provider: MCPAuthProvider | None, runtime: ConnectorRuntime, runtime_state: tuple[RuntimeStateArgument, ...], openapi_adapters: OpenApiRuntimeAdapters, persistence_runtime: PersistenceRuntime, *, telemetry: McpTelemetryDependencies, downstream_client_factory: DownstreamClientFactory) -> FastMCP:
    (requested_tool_state, group_permission_runtime_state) = _resolve_runtime_state(runtime_state)
    connector_tool_runtime_state_store = requested_tool_state if requested_tool_state is not None else _default_connector_tool_runtime_state_store(runtime)
    audit_recorder = telemetry.audit_recorder
    metrics_recorder = telemetry.metrics_recorder
    invocation_log_sink = telemetry.invocation_log_sink
    signals = create_mcp_signals(invocation_log_sink, metrics_recorder, audit_recorder)
    publisher = McpInvocationPublisher(signals)
    middleware: list[Middleware] = [McpProtocolMetricsMiddleware(metrics_recorder, clock=time.monotonic), McpAuditMiddleware(recorder=audit_recorder, identity_source=McpAuditIdentityAdapter(), exposure_mode=settings.mcp.connector_tool_exposure_mode)]
    if group_permission_runtime_state is not None:
        auth_check = personal_tool_permission_check(connector_tool_permission_check(group_permission_runtime_state))
        if settings.mcp.auth_debug_enabled:
            middleware.append(MCPAuthDebugMiddleware(auth=auth_check, permission_group_claim=settings.mcp.permission_group_claim))
        else:
            middleware.append(AuthMiddleware(auth=auth_check))
    approval_state_key = settings.connector_security.approval_state_key
    if not approval_state_key:
        if settings.admin_authentication.environment == 'production':
            raise ValueError('Connector approval state key is required in production')
        approval_state_key = secrets.token_urlsafe(48)
    mcp = FastMCP(name=settings.runtime.app_name, auth=auth_provider, middleware=middleware, request_state_security=RequestStateSecurity(keys=[approval_state_key], ttl=300.0, audience=f'{settings.runtime.app_name}:connector-approval'))
    invocation_policy_store = DatabaseConnectorInvocationPolicyStore(persistence_runtime.database)
    invocation_policy = McpConnectorInvocationApprovalPolicy(StoredConnectorInvocationPolicy(invocation_policy_store), nonce_store=DatabaseApprovalNonceStore(persistence_runtime.database), state_codec=ApprovalStateCodec(clock=time.time, random_token=random_approval_token, ttl_seconds=APPROVAL_TTL_SECONDS), caller_capture=CurrentInvocationApprovalCallerCapture())
    mcp.connector_invocation_policy = invocation_policy
    mcp.invocation_signals = signals
    mcp.execution_pipelines = SignalToolExecutionPipelineFactory(signals, invocation_policy)
    mcp.metrics_recorder = metrics_recorder
    await persistence_runtime.readiness.ensure_ready()
    mcp.persistence_runtime = persistence_runtime
    mcp.group_connector_tool_permissions = group_permission_runtime_state
    mcp.openapi_connector_store_factory = ConfiguredOpenApiConnectorStoreFactory(persistence_runtime.database)
    mcp.openapi_configuration_store = await create_encrypted_connector_configuration_store(persistence_runtime.database)
    mcp.openapi_publishing_store = await ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)()
    mcp.capability_activation_store = await create_capability_activation_store(persistence_runtime.database)
    mcp.group_permission_reader_factory = DatabaseGroupPermissionReaderFactory(persistence_runtime.database)
    mcp.permission_group_claim = settings.mcp.permission_group_claim
    mcp.openapi_configuration_secret = settings.connector_security.configuration_secret or LOCAL_CONNECTOR_CONFIGURATION_SECRET
    openapi_config = settings.openapi_connectors
    mcp.openapi_execution_timeout_seconds = openapi_config.execution_read_timeout_seconds
    mcp.openapi_execution_maximum_response_bytes = openapi_config.json_import_max_bytes
    mcp.openapi_outbound_http_client_factory = openapi_adapters.outbound_http_client_factory
    mcp.include_openapi_in_connector_search = settings.mcp.connector_tool_exposure_mode in OPENAPI_CODEMODE_DISCOVERY_EXPOSURE_MODES
    mcp.capability_description_overrides = await ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(persistence_runtime.database).create()
    if settings.feature_toggles.mcp_administrator_enabled:
        group_permission_store = await create_group_permission_store(persistence_runtime.database)
        openapi_connector_store = await mcp.openapi_connector_store_factory.create()
        downstream_stores = await create_downstream_mcp_stores(
            downstream_mcp_infrastructure_settings_from_app_config(settings).credential_secret,
            persistence_runtime.database,
        )
        catalog = AdministratorConfigurationCatalog(
            partial(InMemoryConnectorRegistry, runtime.connector_registrations,
                [str(registration['id']) for registration in runtime.connector_registrations]),
            openapi_connector_store,
            downstream_stores.definitions,
            downstream_stores.catalogs,
        )
        openapi_administrator_configuration = CatalogAdministratorConnectorConfigurationReader(
            catalog,
            mcp.capability_activation_store,
            invocation_policy_store,
            mcp.capability_description_overrides,
            group_permission_store,
        )
        openapi_administrator_mutation = CatalogAdministratorConfigurationMutation(
            persistence_runtime.database,
            catalog,
            openapi_administrator_configuration,
            mcp.capability_description_overrides,
            group_permission_store,
        )
        administrator_connector_configuration = AdministratorConnectorConfigurationService(
            openapi_administrator_configuration,
            openapi_administrator_mutation,
        )
        register_administrator_connector_configuration_tools(
            McpObservedToolRegistrar(mcp, publisher),
            administrator_connector_configuration,
            settings.admin_authentication.membership_claim,
            settings.admin_authentication.required_membership,
        )
    filesystem_content = create_content_driver(
        TypeAdapter(ContentConfig).validate_python(settings.filesystem.content.model_dump())
    )
    register_filesystem_tools(
        McpObservedToolRegistrar(mcp, publisher),
        CurrentFilesystemCallerCapture(
            mcp,
            RuntimeFilesystemGroupClaimFields(group_permission_runtime_state)
            if group_permission_runtime_state is not None
            else StaticFilesystemGroupClaimFields(settings.mcp.permission_group_claim),
        ),
        DatabaseFilesystemServiceFactory(
            persistence_runtime.database, filesystem_content, settings.filesystem.upload_max_bytes,
        ),
    )
    await initialize_openapi_discovery(mcp)
    await _register_connector_capabilities(mcp, runtime, connector_tool_runtime_state_store, signals, mcp.execution_pipelines, settings.mcp.connector_tool_exposure_mode, settings.mcp.connector_code_execution_timeout_seconds, settings.mcp.maximum_uploaded_file_bytes)
    mcp.openapi_codemode_executor = build_openapi_codemode_executor(mcp, mcp.execution_pipelines)
    signals.tool_inventory_observed.send(await read_openapi_tool_inventory(await mcp.openapi_connector_store_factory.create()))
    downstream_permission_policy = UnrestrictedDownstreamToolPermissionPolicy() if group_permission_runtime_state is None else GroupDownstreamToolPermissionPolicy(group_permission_runtime_state)
    await _register_downstream_mcp_provider(mcp, settings, downstream_permission_policy, persistence_runtime.database, invocation_policy, runtime, downstream_client_factory=downstream_client_factory)
    register_agent_instructions(mcp)
    return mcp

@dataclass(frozen=True)
class RuntimePublicToolIdentitySource:
    native_runtimes: tuple[ConnectorRuntime, ...]

    async def identities(self) -> tuple[PublicToolIdentity, ...]:
        identities: list[PublicToolIdentity] = []
        for runtime in self.native_runtimes:
            registrations = runtime.connector_registrations
            registry = InMemoryConnectorRegistry(registrations, [str(registration['id']) for registration in registrations])
            for definition in registry.list_connector_definitions(ConnectorDefinitionFilter(availability='available')):
                identities.extend(PublicToolIdentity(connector_id=definition.metadata.id, tool_name_prefix=definition.tool_name_prefix, operation_name=name) for name in definition.tool_descriptions)
        return tuple(identities)


async def _register_downstream_mcp_provider(mcp: FastMCP, settings: MCPAppSettings, permission_policy: UnrestrictedDownstreamToolPermissionPolicy | GroupDownstreamToolPermissionPolicy, database: Database, invocation_policy: ConnectorInvocationPolicy, *native_runtimes: ConnectorRuntime, downstream_client_factory: DownstreamClientFactory) -> None:
    infrastructure_settings = downstream_mcp_infrastructure_settings_from_app_config(settings)
    stores = await create_downstream_mcp_stores(
        infrastructure_settings.credential_secret, database
    )
    if settings.personal_connections.enabled and settings.personal_connections.oauth_enabled:
        await PersonalDiscoveryPreparation(database, AuthenticatedTextCipher(infrastructure_settings.credential_secret)).prepare()
    discovery = create_downstream_mcp_discovery(infrastructure_settings, create_downstream_mcp_probe(infrastructure_settings, stores.credentials))
    discovery_runtime = create_downstream_discovery_runtime(DownstreamRuntimeStores(definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, publishing=stores.publishing, activations=stores.activations, descriptions=mcp.capability_description_overrides))
    await discovery_runtime.reconcile()
    mcp.downstream_mcp_discovery_runtime = discovery_runtime
    callers = McpPersonalCallerProvider(settings)
    personal_discovery = PersonalDiscoveryOperations(discovery_runtime, callers, stores.personal_tool_discovery, mcp.group_connector_tool_permissions if settings.personal_connections.enabled and settings.personal_connections.oauth_enabled else InMemoryGroupConnectorToolPermissions(group_claim_fields=()), utc_clock, permission_policy)
    personal_runtime: PersonalToolRuntime = DisabledPersonalToolRuntime()
    if settings.personal_connections.enabled and settings.personal_connections.oauth_enabled:
        personal_runtime = McpPersonalToolRuntime(callers, stores.personal_tool_access, create_personal_mcp_transport(), utc_clock)
    provider = ConnectorAwareDownstreamMcpToolProvider(discovery_runtime=discovery_runtime, personal_runtime=personal_runtime, personal_discovery=personal_discovery, definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, publishing=stores.publishing, activations=stores.activations, client_factory=downstream_client_factory, permission_policy=permission_policy, connector_scope='', signals=mcp.invocation_signals, execution_pipelines=mcp.execution_pipelines)
    mcp.invocation_signals.tool_inventory_observed.send(shared_tool_inventory(discovery_runtime.capture().records))
    mcp.downstream_mcp_tool_provider = provider
    mcp.middleware.insert(0, PersonalDiscoveryMiddleware(provider))
    mcp.add_middleware(PersonalToolReservationMiddleware(provider))
    if settings.mcp.connector_tool_exposure_mode == 'flat':
        mcp.add_provider(provider)
    else:
        mcp.add_provider(NativeCapabilityProviderView(provider))
        connector_tool_registry = getattr(mcp, 'connector_tool_registry', None)
        if connector_tool_registry is None:
            raise RuntimeError('Connector tool registry is required for gateway exposure')
        connector_tool_registry.add_gateway_provider(provider)
    connector_tool_registry = getattr(mcp, 'connector_tool_registry', None)
    notifier = connector_tool_registry.client_notifier if connector_tool_registry is not None else install_tool_list_changed_notifier(mcp)
    mcp.capability_list_change_notifier = notifier
    mcp.downstream_mcp_discovery_coordinator = create_downstream_discovery_coordinator(DownstreamDiscoveryStores(definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, health=stores.health, activations=stores.activations, publishing=stores.publishing, unit_of_work=stores.unit_of_work), DownstreamDiscoveryAdapters(discovery=discovery, notifier=notifier, native_capabilities=provider, monotonic_clock=time.monotonic, random_source=random.random, identity_source=RuntimePublicToolIdentitySource(native_runtimes)), DownstreamDiscoveryCoordinatorOptions(refresh_interval_seconds=settings.mcp.downstream_refresh_interval_seconds, maximum_concurrency=settings.mcp.downstream_discovery_concurrency, jitter_ratio=settings.mcp.downstream_discovery_jitter_ratio, maximum_backoff_seconds=settings.mcp.downstream_discovery_maximum_backoff_seconds))
    mcp.downstream_mcp_periodic_discovery_enabled = settings.mcp.downstream_discovery_enabled

def _default_connector_tool_runtime_state_store(runtime: ConnectorRuntime) -> InMemoryConnectorToolRuntimeStateStore:
    store = InMemoryConnectorToolRuntimeStateStore()
    for mapping in runtime.connector_tool_mappings:
        store.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef(mapping.connector_id, mapping.operation_name), status='enabled'))
    return store

async def _register_connector_capabilities(mcp: FastMCP, runtime: ConnectorRuntime, connector_tool_runtime_state_store: InMemoryConnectorToolRuntimeStateStore, signals: McpSignals, execution_pipelines: McpToolExecutionPipelineFactory, connector_tool_exposure_mode: Literal['flat', 'gateway', 'codemode'], connector_code_execution_timeout_seconds: float, maximum_uploaded_file_bytes: int) -> None:
    await register_connector_tools(mcp, connector_registrations=runtime.connector_registrations, connector_configuration_store=runtime.connector_configuration_store, connector_publishing_store=runtime.connector_publishing_store, connector_tool_mappings=runtime.connector_tool_mappings, capability_description_overrides=mcp.capability_description_overrides, connector_tool_runtime_state_store=connector_tool_runtime_state_store, signals=signals, execution_pipelines=execution_pipelines, connector_tool_exposure_mode=connector_tool_exposure_mode, connector_code_execution_timeout_seconds=connector_code_execution_timeout_seconds, maximum_uploaded_file_bytes=maximum_uploaded_file_bytes)
    connector_options = {'connector_registrations': runtime.connector_registrations, 'connector_configuration_store': runtime.connector_configuration_store, 'connector_publishing_store': runtime.connector_publishing_store, 'activation_store': mcp.capability_activation_store}
    await register_connector_prompts(mcp, ConnectorPromptRegistrationOptions(**connector_options, connector_prompt_mappings=runtime.connector_prompt_mappings))
    await register_connector_resources(mcp, ConnectorResourceRegistrationOptions(**connector_options, connector_resource_mappings=runtime.connector_resource_mappings))

def _resolve_runtime_state(runtime_state: tuple[RuntimeStateArgument, ...]) -> RuntimeStateStores:
    if len(runtime_state) > 2:
        raise TypeError('runtime_state accepts at most two values')
    connector_tool_runtime_state_store = runtime_state[0] if len(runtime_state) > 0 else None
    group_permission_runtime_state = runtime_state[1] if len(runtime_state) > 1 else None
    if connector_tool_runtime_state_store is not None and (not isinstance(connector_tool_runtime_state_store, InMemoryConnectorToolRuntimeStateStore)):
        raise TypeError('runtime_state[0] must be InMemoryConnectorToolRuntimeStateStore or None')
    if group_permission_runtime_state is not None and (not isinstance(group_permission_runtime_state, InMemoryGroupConnectorToolPermissions)):
        raise TypeError('runtime_state[1] must be InMemoryGroupConnectorToolPermissions or None')
    return (connector_tool_runtime_state_store, group_permission_runtime_state)

async def load_production_public_app_config() -> PublicAppConfig:
    return await load_configured_public_app_config(load_server_app_config('.env'))

async def load_configured_public_app_config(settings: AppConfig) -> PublicAppConfig:
    private_api_base_url = settings.endpoints.private_api_base_url.strip()
    api_base_url = settings.endpoints.api_base_url.strip()
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    try:
        await persistence_runtime.readiness.ensure_ready()
        if isinstance(settings.connector_store, InMemoryConnectorStoreConfig):
            configured_source_strategy = HttpConnectorRuntimeStateSourceStrategy()
        elif isinstance(settings.connector_store, SQLiteConnectorStoreConfig):
            configured_source_strategy = StoreBackedConnectorRuntimeStateSourceStrategy()
        else:
            raise TypeError('unsupported connector store configuration')
        return PublicAppConfig(settings=settings, connector_runtime=await DefaultConnectorRuntimeFactory(load_connector_plugins, partial(create_encrypted_connector_configuration_store, persistence_runtime.database), ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)).create(settings), source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=configured_source_strategy, stateless_http=settings.mcp.stateless_http, api_base_url=private_api_base_url or api_base_url or None, persistence_runtime=persistence_runtime, telemetry=create_configured_mcp_telemetry(settings))
    except BaseException:
        await persistence_runtime.shutdown()
        raise

async def create_runtime_context(config: PublicAppConfig, *, downstream_client_factory: DownstreamClientFactory, openapi_adapters: OpenApiRuntimeAdapters) -> PublicAppRuntimeContext:
    install_umbod_consent_screen()
    source_strategy = resolve_connector_runtime_state_source_strategy(config.source_stores, config.configured_source_strategy)
    connector_tool_runtime_state_store = config.connector_tool_runtime_state_store if config.connector_tool_runtime_state_store is not None else InMemoryConnectorToolRuntimeStateStore()
    group_permission_runtime_state = config.group_permission_runtime_state
    if group_permission_runtime_state is None and config.settings.mcp.auth_mode != "none":
        group_permission_runtime_state = InMemoryGroupConnectorToolPermissions(group_claim_fields=(config.settings.mcp.permission_group_claim,))
    auth_provider = config.auth_provider if config.auth_provider is not None else MCPAuthProviderFactory().create(config.settings)
    persistence_runtime = config.persistence_runtime
    mcp = await build_mcp_with_openapi_adapters(config.settings, auth_provider, config.connector_runtime, (connector_tool_runtime_state_store, group_permission_runtime_state), openapi_adapters, persistence_runtime, telemetry=config.telemetry, downstream_client_factory=downstream_client_factory)
    return PublicAppRuntimeContext(mcp=mcp, http_app=mcp.http_app(path=_MCP_HTTP_PATH, stateless_http=config.stateless_http), telemetry=config.telemetry, settings=config.settings, connector_runtime=config.connector_runtime, connector_tool_runtime_state_store=connector_tool_runtime_state_store, group_permission_runtime_state=group_permission_runtime_state, target_stores=ConnectorStorePair(connector_configuration_store=config.connector_runtime.connector_configuration_store, connector_publishing_store=config.connector_runtime.connector_publishing_store), source_strategy=source_strategy, api_base_url=config.api_base_url, persistence_runtime=persistence_runtime)

async def health_response(_request: Request) -> JSONResponse:
    return JSONResponse({'status': 'ok'})

class DynamicPublicMcpDispatcher:

    def __init__(self, app: ASGIApp, runtime: DownstreamDiscoveryRuntime, health: RuntimeProjectionHealth) -> None:
        self._app = app
        self._runtime = runtime
        self._health = health

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get('path', '')
        if logger.isEnabledFor(logging.DEBUG):
            headers = {key.decode('latin-1').lower(): value.decode('latin-1') for (key, value) in scope.get('headers', [])}
            logger.debug('MCP HTTP request received', extra={'mcp_event': 'http_request', 'mcp_http_method': scope.get('method'), 'mcp_request_path': path, 'mcp_session_id_header': headers.get('mcp-session-id')})
        if path.startswith(_MCP_HTTP_PATH) and not self._health.ready:
            await JSONResponse({'detail': 'Runtime synchronization unavailable'}, status_code=503)(scope, receive, send)
            return
        if path == _MCP_HTTP_PATH or not path.startswith('/mcp/proxies/'):
            await self._app(scope, receive, send)
            return
        path_parts = path.split('/', 4)
        public_path = '/'.join(path_parts[:4])
        downstream_subpath = f'/{path_parts[4]}' if len(path_parts) == 5 else ''
        try:
            snapshot = self._runtime.capture()
        except DownstreamDiscoveryUnavailable:
            await JSONResponse({'detail': 'Runtime synchronization unavailable'}, status_code=503)(scope, receive, send)
            return
        definition = next((definition for definition in snapshot.definitions if definition.public_path == public_path and definition.connector_id in snapshot.published_connector_ids), None)
        if definition is None:
            await JSONResponse({'detail': 'Not found'}, status_code=404)(scope, receive, send)
            return
        from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
        token = set_request_connector_scope(definition.connector_id)
        rewritten_path = f'{_MCP_HTTP_PATH}{downstream_subpath}'
        rewritten_scope = {**scope, 'path': rewritten_path, 'raw_path': rewritten_path.encode()}
        try:
            await self._app(rewritten_scope, receive, send)
        finally:
            reset_request_connector_scope(token)

async def build_starlette_app(context: PublicAppRuntimeContext) -> Starlette:
    remote_url = f"{context.settings.endpoints.mcp_base_url.rstrip('/')}{_MCP_HTTP_PATH}"
    health = RuntimeProjectionHealth()
    context.mcp.runtime_projection_health = health

    async def runtime_health_response(request: Request) -> JSONResponse:
        if health.ready:
            return await health_response(request)
        return JSONResponse({'status': 'unavailable', 'runtime_synchronization_failed': health.failed, 'runtime_last_applied_sequence': health.last_applied_sequence}, status_code=503)

    server_card: dict[str, object] = {'$schema': 'https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json', 'name': 'tech.computerlove/umbod', 'title': 'Umbod MCP', 'version': '0.0.1', 'description': 'Umbod MCP server for connector-backed tools.', 'remotes': [{'type': 'streamable-http', 'url': remote_url, 'supportedProtocolVersions': ['2025-06-18']}]}
    return Starlette(routes=[Route(_HEALTH_ROUTE, runtime_health_response, methods=['GET']), Route('/.well-known/mcp/server-card.json', lambda _request: JSONResponse(server_card, headers=_CORS_HEADERS), methods=['GET']), Route(_LOGO_ROUTE, lambda _request: FileResponse(_LOGO_FILE, media_type='image/png'), methods=['GET']), Mount('/', app=DynamicPublicMcpDispatcher(context.http_app, context.mcp.downstream_mcp_discovery_runtime, health))], lifespan=_create_public_http_lifespan(context))

async def create_production_app() -> Starlette:
    from umbod.hosting import create_mcp_app

    return await create_mcp_app(load_server_app_config('.env'), auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)

async def create_configured_production_app(settings: AppConfig) -> Starlette:
    from umbod.hosting import create_mcp_app

    return await create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)

def runtime_state_synchronizer_options(context: PublicAppRuntimeContext) -> ConnectorRuntimeStateSynchronizerOptions | None:
    if context.api_base_url is None and not isinstance(context.source_strategy, LocalConnectorRuntimeStateSourceStrategy):
        return None
    configuration_store = context.target_stores.connector_configuration_store
    publishing_store = context.target_stores.connector_publishing_store
    if configuration_store is None or publishing_store is None:
        return None
    target_stores = LocalConnectorRuntimeStateSourceStrategy(configuration_store, publishing_store)
    if isinstance(context.source_strategy, LocalConnectorRuntimeStateSourceStrategy):
        registrations = context.connector_runtime.connector_registrations
        connector_registry = InMemoryConnectorRegistry(registrations, [str(registration['id']) for registration in registrations])
        source_configuration = context.source_strategy.connector_configuration_store
        source_publishing = context.source_strategy.connector_publishing_store
        reader = StoreBackedConnectorRuntimeStateReader(connector_registry, source_configuration, source_publishing)
        synchronization_source = StoreBackedConnectorRuntimeStateSynchronizationSource(reader) if source_configuration is configuration_store and source_publishing is publishing_store else LocalConnectorRuntimeStateSynchronizationSource(source_configuration, source_publishing)
    elif isinstance(context.source_strategy, StoreBackedConnectorRuntimeStateSourceStrategy):
        registrations = context.connector_runtime.connector_registrations
        connector_registry = InMemoryConnectorRegistry(registrations, [str(registration['id']) for registration in registrations])
        reader = StoreBackedConnectorRuntimeStateReader(connector_registry, configuration_store, publishing_store)
        synchronization_source = StoreBackedConnectorRuntimeStateSynchronizationSource(reader)
    elif isinstance(context.source_strategy, HttpConnectorRuntimeStateSourceStrategy):
        reader = HttpConnectorRuntimeStateReader(context.api_base_url)
        synchronization_source = HttpConnectorRuntimeStateSynchronizationSource(reader)
    else:
        raise TypeError('unsupported connector runtime state source strategy')
    return ConnectorRuntimeStateSynchronizerOptions(mcp=context.mcp, settings=context.settings, database=context.persistence_runtime.database, target_stores=target_stores, reader=reader, synchronization_source=synchronization_source)

def create_connector_runtime_state_synchronizer(options: ConnectorRuntimeStateSynchronizerOptions) -> ConnectorRuntimeStateSynchronizer:
    registry = options.mcp.connector_tool_registry
    return ConnectorRuntimeStateSynchronizer(reader=options.reader, configuration_store=options.target_stores.connector_configuration_store, publishing_store=options.target_stores.connector_publishing_store, tool_registry=registry, synchronization_source=options.synchronization_source)

def _uses_http_runtime_data_readers(context: PublicAppRuntimeContext) -> bool:
    return isinstance(context.source_strategy, HttpConnectorRuntimeStateSourceStrategy) and context.api_base_url is not None


def create_group_permission_runtime_synchronizer(context: PublicAppRuntimeContext, api_base_url: str) -> RuntimeGroupPermissionSynchronizer:
    registry = getattr(context.mcp, 'connector_tool_registry', None)
    notifier = registry.client_notifier if registry is not None else context.mcp.capability_list_change_notifier
    runtime_permissions = context.group_permission_runtime_state
    if runtime_permissions is None:
        raise ValueError("Group permission synchronization requires group permission runtime state")
    reader = HttpGroupPermissionReader(f"{api_base_url.rstrip('/')}/system") if _uses_http_runtime_data_readers(context) else DatabaseGroupPermissionReader(context.persistence_runtime.database)
    return RuntimeGroupPermissionSynchronizer(permission_state_reloader=GroupPermissionStateReloader(permission_reader=reader, runtime_permissions=runtime_permissions), client_notifier=notifier)

def _create_public_http_lifespan(context: PublicAppRuntimeContext) -> object:

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        try:
            await context.persistence_runtime.readiness.ensure_ready()
            synchronizer = await _initialize_runtime_projection(context)
            async with AsyncExitStack() as stack:
                await stack.enter_async_context(context.http_app.lifespan(context.http_app))
                if context.settings.mcp.metrics_enabled:
                    metrics_server = context.telemetry.metrics_server_factory.create()
                    await metrics_server.start()
                    stack.push_async_callback(metrics_server.stop)
                downstream_coordinator: DownstreamDiscoveryCoordinator | None = getattr(context.mcp, 'downstream_mcp_discovery_coordinator', None)
                if downstream_coordinator is not None:
                    await downstream_coordinator.initialize_native_capabilities()
                synchronizer_task = asyncio.create_task(synchronizer.run())
                downstream_task = asyncio.create_task(downstream_coordinator.run()) if downstream_coordinator is not None and getattr(context.mcp, 'downstream_mcp_periodic_discovery_enabled', False) else None
                try:
                    yield
                finally:
                    if downstream_coordinator is not None:
                        downstream_coordinator.stop()
                    if downstream_task is not None:
                        downstream_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await downstream_task
                    synchronizer.stop()
                    synchronizer_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await synchronizer_task
                    flush_logging()
        finally:
            await context.persistence_runtime.shutdown()
    return lifespan

def _create_runtime_projection_synchronizer(context: PublicAppRuntimeContext) -> RuntimeProjectionSynchronizer:
    transport = context.settings.mcp.messaging_transport
    if transport == 'http' and context.api_base_url is None:
        transport = 'sql'
    adapters = McpMessagingAdapterFactory(transport, context.api_base_url or '', context.persistence_runtime.database)
    health = context.mcp.runtime_projection_health
    uses_http_readers = _uses_http_runtime_data_readers(context)

    async def reconcile() -> None:
        await context.mcp.downstream_mcp_discovery_coordinator.reconcile_native_capabilities()
        await reconcile_openapi_discovery(context.mcp)
        if uses_http_readers:
            options = runtime_state_synchronizer_options(context)
            if options is None:
                raise ValueError('HTTP runtime synchronization requires source options')
            await create_connector_runtime_state_synchronizer(options).sync_all()
            tool_synchronizer = ConnectorToolRuntimeStateSynchronizer(reader=HttpConnectorToolRuntimeStateReader(context.api_base_url), store=context.connector_tool_runtime_state_store, reconciler=context.mcp.connector_tool_registry)
            for mapping in context.connector_runtime.connector_tool_mappings:
                await tool_synchronizer.sync_runtime_state(ConnectorToolRef(mapping.connector_id, mapping.operation_name))
        else:
            for mapping in context.connector_runtime.connector_tool_mappings:
                ref = CapabilityRef(connector_kind='native', connector_id=mapping.connector_id, capability_kind='tool', capability_key=mapping.operation_name)
                status = await context.mcp.capability_activation_store.get_status(ref)
                state = ConnectorToolRuntimeState(key=ConnectorToolRef(mapping.connector_id, mapping.operation_name), status='enabled' if status == ActivationStatus.ENABLED else 'disabled')
                context.connector_tool_runtime_state_store.save_runtime_state(state)
        tool_registry = getattr(context.mcp, 'connector_tool_registry', None)
        if tool_registry is not None:
            await tool_registry.reconcile_all()
        for registry in (getattr(context.mcp, 'connector_prompt_registry', None), getattr(context.mcp, 'connector_resource_registry', None)):
            if registry is not None:
                await registry.reconcile_all()
        if context.group_permission_runtime_state is not None:
            await create_group_permission_runtime_synchronizer(context, context.api_base_url or '').sync_group_permissions()
        notifier = tool_registry.client_notifier if tool_registry is not None else context.mcp.capability_list_change_notifier
        notifier.notify_tool_list_changed()
        notifier.notify_prompt_list_changed()
        notifier.notify_resource_list_changed()

    return RuntimeProjectionSynchronizer(adapters.create_projection_reader(), adapters.create_checkpoint_store(), reconcile, health, interval_seconds=1.0, batch_limit=100)


async def _initialize_runtime_projection(context: PublicAppRuntimeContext) -> RuntimeProjectionSynchronizer:
    if isinstance(context.source_strategy, LocalConnectorRuntimeStateSourceStrategy):
        options = runtime_state_synchronizer_options(context)
        if options is None:
            raise ValueError('Local native synchronization requires target stores')
        await create_connector_runtime_state_synchronizer(options).sync_all()
    synchronizer = _create_runtime_projection_synchronizer(context)
    await asyncio.wait_for(synchronizer.bootstrap(), timeout=_INITIAL_RUNTIME_STATE_SYNC_TIMEOUT_SECONDS)
    return synchronizer

def api_base_url_from_settings(settings: MCPAppSettings) -> str | None:
    private_api_base_url = settings.endpoints.private_api_base_url.strip()
    if private_api_base_url:
        return private_api_base_url
    api_base_url = settings.endpoints.api_base_url.strip()
    return api_base_url or None
