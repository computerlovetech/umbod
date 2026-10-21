from typing import Annotated

from fastapi import Depends

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.factory import create_personal_mcp_transport
from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipalProvider, VerifiedGroupMembership
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime, PersonalRuntimeContext, PersonalToolRuntime, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .dependencies import get_personal_group_membership, get_personal_principal_provider


class RestPersonalRuntimeContextProvider:
    def __init__(self, principal: CanonicalPrincipalProvider, groups: VerifiedGroupMembership) -> None:
        self._principal = principal
        self._groups = groups

    async def get_context(self) -> PersonalRuntimeContext:
        principal = await self._principal.get_principal()
        if principal is None:
            raise PersonalRuntimeUnavailable("Personal identity unavailable")
        return PersonalRuntimeContext(principal=principal, group_ids=self._groups.group_ids)


def get_personal_tool_runtime(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[VerifiedGroupMembership, Depends(get_personal_group_membership)],
) -> PersonalToolRuntime:
    if not (factories.settings.personal_connections.enabled and factories.settings.personal_connections.oauth_enabled):
        return DisabledPersonalToolRuntime()
    return PersonalToolRuntimeService(RestPersonalRuntimeContextProvider(principal, groups), stores.definitions, stores.personal_tool_access, create_personal_mcp_transport(), utc_clock)
