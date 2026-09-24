from dataclasses import dataclass

from fastmcp import FastMCP
from starlette.applications import Starlette

from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.mcp.auth import MCPAuthProvider
from umbod.mcp.connectors import (
    ConnectorRuntimeStateReader,
    ConnectorRuntimeStateSynchronizationSource,
)
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.runtime_options import (
    ConnectorRuntimeSourceStores,
    ConnectorRuntimeStateSourceStrategy,
    ConnectorStorePair,
    LocalConnectorRuntimeStateSourceStrategy,
)
from umbod.mcp.metrics import PrometheusMcpMetricsRecorder
from umbod.mcp.settings import MCPAppSettings


@dataclass(frozen=True)
class PublicAppConfig:
    settings: MCPAppSettings
    connector_runtime: ConnectorRuntime
    source_stores: ConnectorRuntimeSourceStores
    configured_source_strategy: ConnectorRuntimeStateSourceStrategy
    stateless_http: bool
    api_base_url: str | None
    persistence_runtime: PersistenceRuntime
    auth_provider: MCPAuthProvider | None = None
    connector_tool_runtime_state_store: InMemoryConnectorToolRuntimeStateStore | None = None
    group_permission_runtime_state: InMemoryGroupConnectorToolPermissions | None = None


@dataclass(frozen=True)
class ConnectorRuntimeStateSynchronizerOptions:
    mcp: FastMCP
    settings: MCPAppSettings
    database: Database
    target_stores: LocalConnectorRuntimeStateSourceStrategy
    reader: ConnectorRuntimeStateReader
    synchronization_source: ConnectorRuntimeStateSynchronizationSource


@dataclass(frozen=True)
class PublicAppRuntimeContext:
    mcp: FastMCP
    http_app: Starlette
    metrics_recorder: PrometheusMcpMetricsRecorder
    settings: MCPAppSettings
    connector_runtime: ConnectorRuntime
    connector_tool_runtime_state_store: InMemoryConnectorToolRuntimeStateStore
    group_permission_runtime_state: InMemoryGroupConnectorToolPermissions | None
    target_stores: ConnectorStorePair
    source_strategy: ConnectorRuntimeStateSourceStrategy
    api_base_url: str | None
    persistence_runtime: PersistenceRuntime
