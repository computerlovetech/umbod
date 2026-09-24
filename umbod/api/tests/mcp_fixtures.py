from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
import asyncio
from collections.abc import Sequence
from typing import cast
from fastmcp import FastMCP
from starlette.applications import Starlette
from umbod.mcp.auth import MCPAuthProvider, MCPAuthProviderFactory
from umbod.mcp.connectors import create_default_mcp_connector_runtime
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.public_app import build_mcp, build_starlette_app, create_runtime_context
from umbod.mcp.runtime_options import ConnectorRuntimeOptions, ConnectorRuntimeSourceStores, HttpConnectorRuntimeStateSourceStrategy, resolve_connector_runtime
from umbod.mcp.settings import MCPAppSettings
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.connectors.native.runtime import ConnectorRuntime, ConnectorToolMapping

def runtime_options_from_kwargs(kwargs: dict[str, object]) -> ConnectorRuntimeOptions:
    kwargs.pop('connector_tool_runtime_state_store', None)
    if 'runtime_options' in kwargs:
        runtime_options = kwargs.pop('runtime_options')
        if not isinstance(runtime_options, ConnectorRuntimeOptions):
            raise TypeError('runtime_options must be ConnectorRuntimeOptions')
        if kwargs:
            unknown_keyword = next(iter(kwargs))
            raise TypeError(f"build_test_mcp() got an unexpected keyword argument '{unknown_keyword}'")
        return runtime_options
    runtime_options = ConnectorRuntimeOptions(connector_runtime=cast(ConnectorRuntime | None, kwargs.pop('connector_runtime', None)), connector_registrations=cast(Sequence[object] | None, kwargs.pop('connector_registrations', None)), connector_configuration_store=cast(ConnectorCurrentConfigurationStore | None, kwargs.pop('connector_configuration_store', None)), connector_publishing_store=cast(ConnectorPublishingStore | None, kwargs.pop('connector_publishing_store', None)), connector_tool_mappings=cast(Sequence[ConnectorToolMapping] | None, kwargs.pop('connector_tool_mappings', None)))
    if kwargs:
        unknown_keyword = next(iter(kwargs))
        raise TypeError(f"build_test_mcp() got an unexpected keyword argument '{unknown_keyword}'")
    return runtime_options

async def build_test_mcp(settings: MCPAppSettings | None=None, auth_provider: MCPAuthProvider | None=None, **kwargs: object) -> FastMCP:
    resolved_settings = settings or MCPAppSettings()
    connector_tool_runtime_state_store = cast(InMemoryConnectorToolRuntimeStateStore | None, kwargs.pop('connector_tool_runtime_state_store', None))
    group_permission_runtime_state = cast(InMemoryGroupConnectorToolPermissions | None, kwargs.pop('group_permission_runtime_state', None))
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(resolved_settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    resolved_runtime = await resolve_connector_runtime(resolved_settings, runtime_options_from_kwargs(kwargs), persistence_runtime)
    resolved_auth_provider = auth_provider or MCPAuthProviderFactory().create(resolved_settings)
    return await build_mcp(resolved_settings, resolved_auth_provider, resolved_runtime, persistence_runtime, connector_tool_runtime_state_store, group_permission_runtime_state)

def create_test_mcp_http_app(settings: MCPAppSettings, auth_provider: MCPAuthProvider | None=None) -> Starlette:

    async def _build() -> Starlette:
        persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
        await persistence_runtime.readiness.ensure_ready()
        config = PublicAppConfig(settings=settings, connector_runtime=await create_default_mcp_connector_runtime(settings, persistence_runtime), auth_provider=auth_provider, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=HttpConnectorRuntimeStateSourceStrategy(), stateless_http=False, api_base_url=None, persistence_runtime=persistence_runtime)
        return await build_starlette_app(await create_runtime_context(config))
    return asyncio.run(_build())
