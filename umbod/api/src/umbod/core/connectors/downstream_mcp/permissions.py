from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
)
from umbod.core.permissions import AssignablePermissionCatalog
from umbod.core.permissions.domain import (
    AssignableConnectorPermissionTarget,
    AssignablePermissionTargets,
    ConnectorCapabilityRef,
    ConnectorToolRef,
)
from umbod.core.publishing import ConnectorPublicationReader


class PersonalDownstreamPermissionCatalog:
    def __init__(
        self,
        catalog: AssignablePermissionCatalog,
        definitions: ConnectorDefinitionStore,
        publishing: ConnectorPublicationReader,
    ) -> None:
        self._catalog = catalog
        self._definitions = definitions
        self._publishing = publishing

    async def has_connector(self, connector_id: str) -> bool:
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if isinstance(result, ConnectorDefinitionFound) and uses_personal_oauth(result.definition):
            return await self._publishing.is_published(connector_id)
        return await self._catalog.has_connector(connector_id)

    async def has_capability(self, capability: ConnectorCapabilityRef) -> bool:
        return await self._catalog.has_capability(capability)

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self._catalog.has_tool(tool)

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        targets = await self._catalog.list_assignable_targets()
        connectors = {item.connector_id: item for item in targets.connectors}
        for definition in (await self._definitions.list()).definitions:
            if uses_personal_oauth(definition) and await self._publishing.is_published(
                definition.connector_id
            ):
                connectors[definition.connector_id] = AssignableConnectorPermissionTarget(
                    connector_id=definition.connector_id,
                    display_name=definition.display_name,
                )
        return AssignablePermissionTargets(
            connectors=tuple(connectors[key] for key in sorted(connectors)),
            capabilities=targets.capabilities,
        )
