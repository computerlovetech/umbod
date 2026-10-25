from typing import Annotated

from fastapi import Depends

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.factory import create_personal_mcp_transport
from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCaller
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime, PersonalToolRuntime, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .dependencies import get_personal_caller


def get_personal_tool_runtime(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    caller: Annotated[PersonalCaller, Depends(get_personal_caller)],
) -> PersonalToolRuntime:
    if not (factories.settings.personal_connections.enabled and factories.settings.personal_connections.oauth_enabled):
        return DisabledPersonalToolRuntime()
    return PersonalToolRuntimeService(caller, stores.definitions, stores.personal_tool_access, create_personal_mcp_transport(), utc_clock)
