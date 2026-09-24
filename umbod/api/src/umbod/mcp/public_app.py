import asyncio
import logging
import random
import secrets
import time

from umbod.core.connectors.downstream_mcp.adapters.composition import create_downstream_mcp_connections

from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.publishing.factories import ConfiguredConnectorPublishingStoreFactory
from umbod.core.activation.factories import create_capability_activation_store
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.administrator.connector_configuration import AdministratorConnectorConfigurationService
from umbod.core.connectors.openapi.administrator_configuration import OpenApiAdministratorConnectorConfigurationReader
from umbod.core.connectors.openapi.administrator_configuration_mutation import OpenApiAdministratorConfigurationMutation
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider

from collections.abc import AsyncIterator
from dataclasses import dataclass
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from fastmcp import FastMCP
from fastmcp.server.middleware import AuthMiddleware, Middleware
from mcp.server.request_state import RequestStateSecurity
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send
from umbod.core.connectors.native.bootstrap import DefaultConnectorRuntimeFactory
from umbod.core.invocation import ConnectorInvocationPolicy, StoredConnectorInvocationPolicy
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import InMemoryConnectorRegistry
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionStore, PublicPathQuery
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.activation.events import ConnectorCapabilityActivationChanged
from umbod_sdk.connectors.discovery import load_connector_plugins
from umbod.mcp.administrator import register_administrator_connector_configuration_tools
from umbod.mcp.auth import MCPAuthProviderFactory
from umbod.mcp.auth.consent_screen import install_umbod_consent_screen
from umbod.mcp.auth.factory import MCPAuthProvider
from umbod.mcp.auth.debug_middleware import MCPAuthDebugMiddleware
from umbod.mcp.context import ConnectorRuntimeStateSynchronizerOptions, PublicAppConfig, PublicAppRuntimeContext
from umbod.core.invocation import DatabaseApprovalNonceStore
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.mcp.connectors import (
    APPROVAL_TTL_SECONDS,
    CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT,
    CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS,
    ApprovalStateCodec,
    ConnectorPublicationPollingSynchronizer,
    ConnectorRuntimeStateChangePollingSynchronizer,
    ConnectorRuntimeStateSynchronizer,
    CurrentInvocationApprovalPrincipalProvider,
    HttpConnectorRuntimeStateReader,
    HttpConnectorRuntimeStateSynchronizationSource,
    LocalConnectorRuntimeStateSynchronizationSource,
    McpConnectorInvocationApprovalPolicy,
    StoreBackedConnectorRuntimeStateReader,
    StoreBackedConnectorRuntimeStateSynchronizationSource,
    random_approval_token,
)
from umbod.mcp.connectors.prompts import ConnectorPromptRegistrationOptions, register_connector_prompts
from umbod.mcp.connectors.resources import ConnectorResourceRegistrationOptions, register_connector_resources
from umbod.mcp.connectors.tools import (
    ConnectorToolChangePollingSynchronizer,
    ConnectorToolRuntimeStateSynchronizer,
    HttpConnectorToolRuntimeStateReader,
    InMemoryConnectorToolRuntimeStateStore,
    install_tool_list_changed_notifier,
    register_connector_tools,
)
from umbod.mcp.metrics import McpMetricsRecorder, PrometheusMcpMetricsRecorder
from umbod.mcp.metrics.http_server import McpMetricsHttpServer
from umbod.mcp.logging import ConnectorToolInvocationLogger, McpAuditIdentityAdapter, McpToolInvocationLogSink, create_default_connector_tool_invocation_logger, create_default_mcp_audit_recorder, create_default_mcp_tool_invocation_log_sink
from umbod.mcp.middleware import McpAuditMiddleware
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.invocation import McpToolInvocationObserver
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.mcp.downstream_mcp_connectors.coordinator import DownstreamDiscoveryAdapters, DownstreamDiscoveryCoordinator, DownstreamDiscoveryCoordinatorOptions, DownstreamDiscoveryStores, create_downstream_discovery_coordinator
from umbod.mcp.downstream_mcp_connectors.provider import ConnectorAwareDownstreamMcpToolProvider, GroupDownstreamToolPermissionPolicy, NativeCapabilityProviderView, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.live_permission_updates import GROUP_PERMISSION_CHANGE_POLL_BATCH_LIMIT, GROUP_PERMISSION_CHANGE_POLL_INTERVAL_SECONDS, GroupPermissionChangePollingSynchronizer, GroupPermissionStateReloader, HttpGroupPermissionReader, RuntimeGroupPermissionSynchronizer
from umbod.core.connectors.openapi.execution import OutboundHttpClientFactory
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions, connector_tool_permission_check
from umbod.mcp.openapi_connectors import DatabaseGroupPermissionReaderFactory, OutboundHttpClientFactoryPort, build_openapi_codemode_executor
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, ConnectorStorePair, HttpConnectorRuntimeStateSourceStrategy, LocalConnectorRuntimeStateSourceStrategy, StoreBackedConnectorRuntimeStateSourceStrategy, resolve_connector_runtime_state_source_strategy
from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.config import AppConfig, InMemoryConnectorStoreConfig, SQLiteConnectorStoreConfig, load_app_config
from umbod.logging import flush_logging
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.messaging import McpMessagingAdapterFactory
_CORS_HEADERS = {'Access-Control-Allow-Origin': '*'}
_MCP_HTTP_PATH = '/mcp'
_HEALTH_ROUTE = '/system/health'
_LOGO_ROUTE = '/assets/logo.png'
_LOGO_FILE = Path(__file__).resolve().parent / 'assets' / 'logo.png'
_STARTUP_SYNC_RETRY_DELAY_SECONDS = 1.0
_INITIAL_RUNTIME_STATE_SYNC_TIMEOUT_SECONDS = 60.0
logger = logging.getLogger(__name__)
PollingSynchronizer = ConnectorPublicationPollingSynchronizer | ConnectorRuntimeStateChangePollingSynchronizer | ConnectorToolChangePollingSynchronizer | GroupPermissionChangePollingSynchronizer
RuntimeStateArgument = InMemoryConnectorToolRuntimeStateStore | InMemoryGroupConnectorToolPermissions | None
RuntimeStateStores = tuple[InMemoryConnectorToolRuntimeStateStore | None, InMemoryGroupConnectorToolPermissions | None]
OpenApiCodemodeDiscoveryExposureMode = Literal['codemode']
OPENAPI_CODEMODE_DISCOVERY_EXPOSURE_MODES: frozenset[OpenApiCodemodeDiscoveryExposureMode] = frozenset({'codemode'})

@dataclass(frozen=True)
class OpenApiRuntimeAdapters:
    outbound_http_client_factory: OutboundHttpClientFactoryPort

async def build_mcp(settings: MCPAppSettings, auth_provider: MCPAuthProvider | None, runtime: ConnectorRuntime, persistence_runtime: PersistenceRuntime, *runtime_state: RuntimeStateArgument) -> FastMCP:
    return await build_mcp_with_openapi_adapters(settings, auth_provider, runtime, runtime_state, _default_openapi_runtime_adapters(settings), persistence_runtime)

async def build_mcp_with_openapi_adapters(settings: MCPAppSettings, auth_provider: MCPAuthProvider | None, runtime: ConnectorRuntime, runtime_state: tuple[RuntimeStateArgument, ...], openapi_adapters: OpenApiRuntimeAdapters, persistence_runtime: PersistenceRuntime) -> FastMCP:
    (requested_tool_state, group_permission_runtime_state) = _resolve_runtime_state(runtime_state)
    connector_tool_runtime_state_store = requested_tool_state if requested_tool_state is not None else _default_connector_tool_runtime_state_store(runtime)
    audit_recorder = create_default_mcp_audit_recorder(settings.runtime.app_name)
    metrics_recorder = PrometheusMcpMetricsRecorder()
    invocation_log_sink = create_default_mcp_tool_invocation_log_sink()
    tool_invocation_logger = create_default_connector_tool_invocation_logger(invocation_log_sink, audit_recorder)
    middleware: list[Middleware] = [McpAuditMiddleware(recorder=audit_recorder, identity_source=McpAuditIdentityAdapter(), exposure_mode=settings.mcp.connector_tool_exposure_mode)]
    if group_permission_runtime_state is not None:
        auth_check = connector_tool_permission_check(group_permission_runtime_state)
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
    invocation_policy = McpConnectorInvocationApprovalPolicy(StoredConnectorInvocationPolicy(invocation_policy_store), nonce_store=DatabaseApprovalNonceStore(persistence_runtime.database), state_codec=ApprovalStateCodec(clock=time.time, random_token=random_approval_token, ttl_seconds=APPROVAL_TTL_SECONDS), principal_provider=CurrentInvocationApprovalPrincipalProvider())
    mcp.connector_invocation_policy = invocation_policy
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
        openapi_administrator_configuration = OpenApiAdministratorConnectorConfigurationReader(
            openapi_connector_store,
            mcp.capability_activation_store,
            invocation_policy_store,
            mcp.capability_description_overrides,
            group_permission_store,
        )
        openapi_administrator_mutation = OpenApiAdministratorConfigurationMutation(
            persistence_runtime.database,
            openapi_connector_store,
            openapi_administrator_configuration,
            mcp.capability_description_overrides,
            group_permission_store,
        )
        administrator_connector_configuration = AdministratorConnectorConfigurationService(
            openapi_administrator_configuration,
            openapi_administrator_mutation,
        )
        register_administrator_connector_configuration_tools(
            McpObservedToolRegistrar(mcp, McpToolInvocationObserver(tool_invocation_logger, metrics_recorder)),
            administrator_connector_configuration,
            settings.admin_authentication.membership_claim,
            settings.admin_authentication.required_membership,
        )
    await _register_connector_capabilities(mcp, runtime, connector_tool_runtime_state_store, audit_recorder, invocation_log_sink, tool_invocation_logger, metrics_recorder, settings.mcp.connector_tool_exposure_mode, settings.mcp.connector_code_execution_timeout_seconds, settings.mcp.maximum_uploaded_file_bytes, invocation_policy)
    mcp.openapi_codemode_executor = build_openapi_codemode_executor(mcp, mcp.connector_tool_invocation_logger)
    downstream_permission_policy = UnrestrictedDownstreamToolPermissionPolicy() if group_permission_runtime_state is None else GroupDownstreamToolPermissionPolicy(group_permission_runtime_state)
    await _register_downstream_mcp_provider(mcp, settings, downstream_permission_policy, persistence_runtime.database, invocation_policy)
    return mcp

async def _register_downstream_mcp_provider(mcp: FastMCP, settings: MCPAppSettings, permission_policy: UnrestrictedDownstreamToolPermissionPolicy | GroupDownstreamToolPermissionPolicy, database: Database, invocation_policy: ConnectorInvocationPolicy) -> None:
    infrastructure_settings = downstream_mcp_infrastructure_settings_from_app_config(settings)
    stores = await create_downstream_mcp_stores(
        infrastructure_settings.credential_secret, database
    )
    connections = create_downstream_mcp_connections(infrastructure_settings, stores.credentials)
    provider = ConnectorAwareDownstreamMcpToolProvider(definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, publishing=stores.publishing, activations=stores.activations, client_factory=connections.client_factory, permission_policy=permission_policy, connector_scope='', capability_description_overrides=mcp.capability_description_overrides, tool_invocation_logger=mcp.connector_tool_invocation_logger, metrics_recorder=mcp.metrics_recorder, invocation_policy=invocation_policy)
    mcp.downstream_mcp_tool_provider = provider
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
    mcp.downstream_mcp_discovery_coordinator = create_downstream_discovery_coordinator(DownstreamDiscoveryStores(definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, health=stores.health, activations=stores.activations, publishing=stores.publishing), DownstreamDiscoveryAdapters(discovery=connections.discovery, notifier=notifier, native_capabilities=provider, monotonic_clock=time.monotonic, random_source=random.random), DownstreamDiscoveryCoordinatorOptions(refresh_interval_seconds=settings.mcp.downstream_refresh_interval_seconds, maximum_concurrency=settings.mcp.downstream_discovery_concurrency, jitter_ratio=settings.mcp.downstream_discovery_jitter_ratio, maximum_backoff_seconds=settings.mcp.downstream_discovery_maximum_backoff_seconds))
    mcp.downstream_mcp_periodic_discovery_enabled = settings.mcp.downstream_discovery_enabled

def _default_openapi_runtime_adapters(settings: MCPAppSettings) -> OpenApiRuntimeAdapters:
    openapi_config = settings.openapi_connectors
    return OpenApiRuntimeAdapters(outbound_http_client_factory=OutboundHttpClientFactory(connect_timeout_seconds=openapi_config.execution_connect_timeout_seconds, read_timeout_seconds=openapi_config.execution_read_timeout_seconds, write_timeout_seconds=openapi_config.execution_write_timeout_seconds, pool_timeout_seconds=openapi_config.execution_pool_timeout_seconds))

def _default_connector_tool_runtime_state_store(runtime: ConnectorRuntime) -> InMemoryConnectorToolRuntimeStateStore:
    store = InMemoryConnectorToolRuntimeStateStore()
    for mapping in runtime.connector_tool_mappings:
        store.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef(mapping.connector_id, mapping.operation_name), status='enabled'))
    return store

async def _register_connector_capabilities(mcp: FastMCP, runtime: ConnectorRuntime, connector_tool_runtime_state_store: InMemoryConnectorToolRuntimeStateStore, audit_recorder: object, invocation_log_sink: McpToolInvocationLogSink, tool_invocation_logger: ConnectorToolInvocationLogger, metrics_recorder: McpMetricsRecorder, connector_tool_exposure_mode: Literal['flat', 'gateway', 'codemode'], connector_code_execution_timeout_seconds: float, maximum_uploaded_file_bytes: int, invocation_policy: ConnectorInvocationPolicy) -> None:
    mcp.metrics_recorder = metrics_recorder
    mcp.connector_tool_invocation_logger = tool_invocation_logger
    await register_connector_tools(mcp, connector_registrations=runtime.connector_registrations, connector_configuration_store=runtime.connector_configuration_store, connector_publishing_store=runtime.connector_publishing_store, connector_tool_mappings=runtime.connector_tool_mappings, capability_description_overrides=mcp.capability_description_overrides, connector_tool_runtime_state_store=connector_tool_runtime_state_store, tool_invocation_log_sink=invocation_log_sink, audit_recorder=audit_recorder, metrics_recorder=metrics_recorder, connector_tool_exposure_mode=connector_tool_exposure_mode, connector_code_execution_timeout_seconds=connector_code_execution_timeout_seconds, maximum_uploaded_file_bytes=maximum_uploaded_file_bytes, invocation_policy=invocation_policy)
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
    return await load_configured_public_app_config(load_app_config('.env'))

async def load_configured_public_app_config(settings: AppConfig) -> PublicAppConfig:
    private_api_base_url = settings.endpoints.private_api_base_url.strip()
    api_base_url = settings.endpoints.api_base_url.strip()
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    if isinstance(settings.connector_store, InMemoryConnectorStoreConfig):
        configured_source_strategy = HttpConnectorRuntimeStateSourceStrategy()
    elif isinstance(settings.connector_store, SQLiteConnectorStoreConfig):
        configured_source_strategy = StoreBackedConnectorRuntimeStateSourceStrategy()
    else:
        raise TypeError('unsupported connector store configuration')
    return PublicAppConfig(settings=settings, connector_runtime=await DefaultConnectorRuntimeFactory(load_connector_plugins, partial(create_encrypted_connector_configuration_store, persistence_runtime.database), ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)).create(settings), source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=configured_source_strategy, stateless_http=settings.mcp.stateless_http, api_base_url=private_api_base_url or api_base_url or None, persistence_runtime=persistence_runtime)

async def create_runtime_context(config: PublicAppConfig) -> PublicAppRuntimeContext:
    install_umbod_consent_screen()
    source_strategy = resolve_connector_runtime_state_source_strategy(config.source_stores, config.configured_source_strategy)
    connector_tool_runtime_state_store = config.connector_tool_runtime_state_store if config.connector_tool_runtime_state_store is not None else InMemoryConnectorToolRuntimeStateStore()
    group_permission_runtime_state = config.group_permission_runtime_state
    if group_permission_runtime_state is None and config.settings.mcp.auth_mode != "none":
        group_permission_runtime_state = InMemoryGroupConnectorToolPermissions(group_claim_fields=(config.settings.mcp.permission_group_claim,))
    auth_provider = config.auth_provider if config.auth_provider is not None else MCPAuthProviderFactory().create(config.settings)
    persistence_runtime = config.persistence_runtime
    mcp = await build_mcp_with_openapi_adapters(config.settings, auth_provider, config.connector_runtime, (connector_tool_runtime_state_store, group_permission_runtime_state), _default_openapi_runtime_adapters(config.settings), persistence_runtime)
    metrics_recorder = mcp.metrics_recorder
    if not isinstance(metrics_recorder, PrometheusMcpMetricsRecorder):
        raise TypeError('MCP metrics recorder must be PrometheusMcpMetricsRecorder')
    return PublicAppRuntimeContext(mcp=mcp, http_app=mcp.http_app(path=_MCP_HTTP_PATH, stateless_http=config.stateless_http), metrics_recorder=metrics_recorder, settings=config.settings, connector_runtime=config.connector_runtime, connector_tool_runtime_state_store=connector_tool_runtime_state_store, group_permission_runtime_state=group_permission_runtime_state, target_stores=ConnectorStorePair(connector_configuration_store=config.connector_runtime.connector_configuration_store, connector_publishing_store=config.connector_runtime.connector_publishing_store), source_strategy=source_strategy, api_base_url=config.api_base_url, persistence_runtime=persistence_runtime)

async def health_response(_request: Request) -> JSONResponse:
    return JSONResponse({'status': 'ok'})

class DynamicPublicMcpDispatcher:

    def __init__(self, app: ASGIApp, definitions: ConnectorDefinitionStore, publishing: ConnectorPublishingStore) -> None:
        self._app = app
        self._definitions = definitions
        self._publishing = publishing

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get('path', '')
        if logger.isEnabledFor(logging.DEBUG):
            headers = {key.decode('latin-1').lower(): value.decode('latin-1') for (key, value) in scope.get('headers', [])}
            logger.debug('MCP HTTP request received', extra={'mcp_event': 'http_request', 'mcp_http_method': scope.get('method'), 'mcp_request_path': path, 'mcp_session_id_header': headers.get('mcp-session-id')})
        if path == _MCP_HTTP_PATH or not path.startswith('/mcp/proxies/'):
            await self._app(scope, receive, send)
            return
        path_parts = path.split('/', 4)
        public_path = '/'.join(path_parts[:4])
        downstream_subpath = f'/{path_parts[4]}' if len(path_parts) == 5 else ''
        result = await self._definitions.get_by_public_path(PublicPathQuery(public_path=public_path))
        if not isinstance(result, ConnectorDefinitionFound) or not await self._publishing.is_published(result.definition.connector_id):
            await JSONResponse({'detail': 'Not found'}, status_code=404)(scope, receive, send)
            return
        from umbod.mcp.downstream_mcp_connectors.provider import reset_request_connector_scope, set_request_connector_scope
        token = set_request_connector_scope(result.definition.connector_id)
        rewritten_path = f'{_MCP_HTTP_PATH}{downstream_subpath}'
        rewritten_scope = {**scope, 'path': rewritten_path, 'raw_path': rewritten_path.encode()}
        try:
            await self._app(rewritten_scope, receive, send)
        finally:
            reset_request_connector_scope(token)

async def build_starlette_app(context: PublicAppRuntimeContext) -> Starlette:
    remote_url = f"{context.settings.endpoints.mcp_base_url.rstrip('/')}{_MCP_HTTP_PATH}"
    downstream_infrastructure_settings = downstream_mcp_infrastructure_settings_from_app_config(context.settings)
    downstream_stores = await create_downstream_mcp_stores(
        downstream_infrastructure_settings.credential_secret,
        context.persistence_runtime.database,
    )
    server_card: dict[str, object] = {'$schema': 'https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json', 'name': 'tech.computerlove/umbod', 'title': 'Umbod MCP', 'version': '0.0.1', 'description': 'Umbod MCP server for connector-backed tools.', 'remotes': [{'type': 'streamable-http', 'url': remote_url, 'supportedProtocolVersions': ['2025-06-18']}]}
    return Starlette(routes=[Route(_HEALTH_ROUTE, health_response, methods=['GET']), Route('/.well-known/mcp/server-card.json', lambda _request: JSONResponse(server_card, headers=_CORS_HEADERS), methods=['GET']), Route(_LOGO_ROUTE, lambda _request: FileResponse(_LOGO_FILE, media_type='image/png'), methods=['GET']), Mount('/', app=DynamicPublicMcpDispatcher(context.http_app, downstream_stores.definitions, downstream_stores.publishing))], lifespan=_create_public_http_lifespan(context))

async def create_production_app() -> Starlette:
    return await create_configured_production_app(load_app_config('.env'))

async def create_configured_production_app(settings: AppConfig) -> Starlette:
    config = await load_configured_public_app_config(settings)
    return await build_starlette_app(await create_runtime_context(config))

def runtime_state_synchronizer_options(context: PublicAppRuntimeContext) -> ConnectorRuntimeStateSynchronizerOptions | None:
    if context.api_base_url is None:
        return None
    configuration_store = context.target_stores.connector_configuration_store
    publishing_store = context.target_stores.connector_publishing_store
    if configuration_store is None or publishing_store is None:
        return None
    target_stores = LocalConnectorRuntimeStateSourceStrategy(configuration_store, publishing_store)
    if isinstance(context.source_strategy, LocalConnectorRuntimeStateSourceStrategy):
        reader = HttpConnectorRuntimeStateReader(context.api_base_url)
        synchronization_source = LocalConnectorRuntimeStateSynchronizationSource(context.source_strategy.connector_configuration_store, context.source_strategy.connector_publishing_store)
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

def create_connector_publication_synchronizer(options: ConnectorRuntimeStateSynchronizerOptions, api_base_url: str, runtime_state_synchronizer: ConnectorRuntimeStateSynchronizer, downstream_coordinator: DownstreamDiscoveryCoordinator) -> ConnectorPublicationPollingSynchronizer:

    async def handle(connector_id: str) -> None:
        await runtime_state_synchronizer.sync_connector(connector_id)
        await downstream_coordinator.reconcile_native_capabilities()
    adapters = McpMessagingAdapterFactory(options.settings.mcp.messaging_transport, api_base_url, options.database)
    return ConnectorPublicationPollingSynchronizer(consumer_id='umbod-mcp-runtime-connectors', checkpoint_store=adapters.create_checkpoint_store(), stream_reader=adapters.create_publication_reader(), handler=handle, interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS, batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT)

def create_connector_runtime_state_change_synchronizer(options: ConnectorRuntimeStateSynchronizerOptions, api_base_url: str, runtime_state_synchronizer: ConnectorRuntimeStateSynchronizer, downstream_coordinator: DownstreamDiscoveryCoordinator) -> ConnectorRuntimeStateChangePollingSynchronizer:

    async def handle(connector_id: str) -> None:
        await runtime_state_synchronizer.sync_connector(connector_id)
        await downstream_coordinator.reconcile_native_capabilities()
    adapters = McpMessagingAdapterFactory(options.settings.mcp.messaging_transport, api_base_url, options.database)
    return ConnectorRuntimeStateChangePollingSynchronizer(consumer_id='umbod-mcp-runtime-state-connectors', checkpoint_store=adapters.create_checkpoint_store(), stream_reader=adapters.create_runtime_state_reader(), handler=handle, interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS, batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT)

def create_capability_description_override_synchronizer(options: ConnectorRuntimeStateSynchronizerOptions, api_base_url: str) -> ConnectorRuntimeStateChangePollingSynchronizer:
    notifier = options.mcp.connector_tool_registry.client_notifier
    adapters = McpMessagingAdapterFactory(options.settings.mcp.messaging_transport, api_base_url, options.database)

    async def handle(_connector_id: str) -> None:
        if notifier is not None:
            notifier.notify_tool_list_changed()
    return ConnectorRuntimeStateChangePollingSynchronizer(consumer_id='umbod-mcp-capability-description-overrides', checkpoint_store=adapters.create_checkpoint_store(), stream_reader=adapters.create_capability_description_override_reader(), handler=handle, interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS, batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT)

def create_connector_tool_runtime_state_synchronizer(context: PublicAppRuntimeContext, api_base_url: str) -> ConnectorToolRuntimeStateSynchronizer:
    return ConnectorToolRuntimeStateSynchronizer(reader=HttpConnectorToolRuntimeStateReader(api_base_url), store=context.connector_tool_runtime_state_store, reconciler=context.mcp.connector_tool_registry)

def create_connector_tool_change_synchronizer(context: PublicAppRuntimeContext, api_base_url: str, runtime_state_synchronizer: ConnectorToolRuntimeStateSynchronizer) -> ConnectorToolChangePollingSynchronizer:
    adapters = McpMessagingAdapterFactory(context.settings.mcp.messaging_transport, api_base_url, context.persistence_runtime.database)
    prompt_registry = getattr(context.mcp, 'connector_prompt_registry', None)
    resource_registry = getattr(context.mcp, 'connector_resource_registry', None)
    tool_registry = getattr(context.mcp, 'connector_tool_registry', None)
    notifier = tool_registry.client_notifier if tool_registry is not None else None

    async def handle(event: ConnectorCapabilityActivationChanged) -> None:
        if event.capability_kind == 'tool':
            await runtime_state_synchronizer.sync_runtime_state(event.key)
            return
        if event.capability_kind == 'prompt':
            if prompt_registry is not None:
                await prompt_registry.reconcile_connector(event.connector_id)
            if notifier is not None:
                notifier.notify_prompt_list_changed()
            return
        if event.capability_kind in ('resource', 'resource_template'):
            if resource_registry is not None:
                await resource_registry.reconcile_connector(event.connector_id)
            if notifier is not None:
                notifier.notify_resource_list_changed()

    return ConnectorToolChangePollingSynchronizer(consumer_id='umbod-mcp-runtime-connector-tools', checkpoint_store=adapters.create_checkpoint_store(), stream_reader=adapters.create_tool_activation_reader(), handler=handle)

def create_group_permission_runtime_synchronizer(context: PublicAppRuntimeContext, api_base_url: str) -> RuntimeGroupPermissionSynchronizer:
    registry = context.mcp.connector_tool_registry
    runtime_permissions = context.group_permission_runtime_state
    if runtime_permissions is None:
        raise ValueError("Group permission synchronization requires group permission runtime state")
    return RuntimeGroupPermissionSynchronizer(permission_state_reloader=GroupPermissionStateReloader(permission_reader=HttpGroupPermissionReader(f"{api_base_url.rstrip('/')}/system"), runtime_permissions=runtime_permissions), client_notifier=registry.client_notifier)

def create_group_permission_change_synchronizer(context: PublicAppRuntimeContext, api_base_url: str, interval_seconds: float, batch_limit: int) -> GroupPermissionChangePollingSynchronizer:
    adapters = McpMessagingAdapterFactory(context.settings.mcp.messaging_transport, api_base_url, context.persistence_runtime.database)
    return GroupPermissionChangePollingSynchronizer(consumer_id='umbod-mcp-runtime-group-permissions', checkpoint_store=adapters.create_checkpoint_store(), stream_reader=adapters.create_group_permission_reader(), runtime_synchronizer=create_group_permission_runtime_synchronizer(context, api_base_url), interval_seconds=interval_seconds, batch_limit=batch_limit)

def _create_public_http_lifespan(context: PublicAppRuntimeContext) -> object:

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        try:
            await context.persistence_runtime.readiness.ensure_ready()
            synchronizers = await _create_public_polling_synchronizers(context)
            async with AsyncExitStack() as stack:
                await stack.enter_async_context(context.http_app.lifespan(context.http_app))
                metrics_server = McpMetricsHttpServer(context.metrics_recorder, context.settings.mcp.metrics_port, '0.0.0.0')
                await metrics_server.start()
                stack.push_async_callback(metrics_server.stop)
                synchronizer_tasks = [asyncio.create_task(synchronizer.run()) if synchronizer is not None else None for synchronizer in synchronizers]
                downstream_coordinator: DownstreamDiscoveryCoordinator | None = getattr(context.mcp, 'downstream_mcp_discovery_coordinator', None)
                if downstream_coordinator is not None:
                    await downstream_coordinator.initialize_native_capabilities()
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
                    for (synchronizer, synchronizer_task) in zip(synchronizers, synchronizer_tasks, strict=True):
                        if synchronizer is not None:
                            synchronizer.stop()
                        if synchronizer_task is not None:
                            synchronizer_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await synchronizer_task
                        flush_logging()
        finally:
            await context.persistence_runtime.shutdown()
    return lifespan

async def _create_public_polling_synchronizers(context: PublicAppRuntimeContext) -> tuple[PollingSynchronizer | None, ...]:
    synchronizer_options = runtime_state_synchronizer_options(context)
    api_base_url = context.api_base_url
    if synchronizer_options is None or api_base_url is None:
        return (None,) * 5
    runtime_synchronizer = create_connector_runtime_state_synchronizer(synchronizer_options)
    tool_synchronizer = create_connector_tool_runtime_state_synchronizer(context, api_base_url)
    logger.info('Initial MCP runtime state synchronization started')
    try:
        await asyncio.wait_for(_sync_initial_public_runtime_states(context, api_base_url, runtime_synchronizer, tool_synchronizer), timeout=_INITIAL_RUNTIME_STATE_SYNC_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.exception('Initial MCP runtime state synchronization exceeded %.1f seconds', _INITIAL_RUNTIME_STATE_SYNC_TIMEOUT_SECONDS)
        raise
    logger.info('Initial MCP runtime state synchronization completed')
    downstream_coordinator = getattr(context.mcp, 'downstream_mcp_discovery_coordinator', None)
    group_permission_change_synchronizer = None
    if context.group_permission_runtime_state is not None:
        group_permission_change_synchronizer = create_group_permission_change_synchronizer(context, api_base_url, GROUP_PERMISSION_CHANGE_POLL_INTERVAL_SECONDS, GROUP_PERMISSION_CHANGE_POLL_BATCH_LIMIT)
    return (create_connector_publication_synchronizer(synchronizer_options, api_base_url, runtime_synchronizer, downstream_coordinator), create_connector_runtime_state_change_synchronizer(synchronizer_options, api_base_url, runtime_synchronizer, downstream_coordinator), create_connector_tool_change_synchronizer(context, api_base_url, tool_synchronizer), create_capability_description_override_synchronizer(synchronizer_options, api_base_url), group_permission_change_synchronizer)

def api_base_url_from_settings(settings: MCPAppSettings) -> str | None:
    private_api_base_url = settings.endpoints.private_api_base_url.strip()
    if private_api_base_url:
        return private_api_base_url
    api_base_url = settings.endpoints.api_base_url.strip()
    return api_base_url or None

async def _sync_initial_public_runtime_states(context: PublicAppRuntimeContext, api_base_url: str, runtime_state_synchronizer: ConnectorRuntimeStateSynchronizer, tool_runtime_state_synchronizer: ConnectorToolRuntimeStateSynchronizer) -> None:
    attempt = 1
    while True:
        try:
            logger.info('Connector runtime state synchronization started')
            await runtime_state_synchronizer.sync_all()
            logger.info('Connector runtime state synchronization completed')
            logger.info('Connector tool runtime state synchronization started')
            for mapping in context.connector_runtime.connector_tool_mappings:
                tool_ref = ConnectorToolRef(connector_id=mapping.connector_id, operation_name=mapping.operation_name)
                await tool_runtime_state_synchronizer.sync_runtime_state(tool_ref)
            logger.info('Connector tool runtime state synchronization completed')
            if context.group_permission_runtime_state is not None:
                group_permission_synchronizer = create_group_permission_runtime_synchronizer(context, api_base_url)
                logger.info('Group permission synchronization started')
                await group_permission_synchronizer.sync_group_permissions()
                logger.info('Group permission synchronization completed')
            return
        except URLError as error:
            logger.warning('Initial MCP runtime state synchronization failed on attempt %s; retrying in %.1f seconds: %s', attempt, _STARTUP_SYNC_RETRY_DELAY_SECONDS, error)
            attempt += 1
            await asyncio.sleep(_STARTUP_SYNC_RETRY_DELAY_SECONDS)
