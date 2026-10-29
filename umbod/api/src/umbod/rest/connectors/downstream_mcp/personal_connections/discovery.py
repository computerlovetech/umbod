from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends

from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCaller, CanonicalPrincipal
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryQuery, PersonalToolDiscoveryReader
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionReader
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .dependencies import get_personal_caller


class PersonalConnectorDiscovery:
    def __init__(self, reader: PersonalToolDiscoveryReader, definitions: ConnectorDefinitionReader, principal: CanonicalPrincipal, enabled: bool, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._definitions = definitions
        self._principal = principal
        self._enabled = enabled
        self._clock = clock

    async def available(self, connector_ids: tuple[str, ...]) -> frozenset[str]:
        if not self._enabled or not connector_ids:
            return frozenset()
        selected = tuple(definition for definition in (await self._definitions.list()).definitions if definition.connector_id in connector_ids)
        records = await self._reader.read(PersonalToolDiscoveryQuery(principal=self._principal, definitions=selected, now=self._clock()))
        return frozenset(record.definition.connector_id for record in records)


def get_personal_connector_discovery(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    caller: Annotated[PersonalCaller, Depends(get_personal_caller)],
) -> PersonalConnectorDiscovery:
    enabled = factories.settings.personal_connections.enabled and factories.settings.personal_connections.oauth_enabled
    return PersonalConnectorDiscovery(stores.personal_tool_discovery, stores.definitions, caller.principal, enabled, utc_clock)
