from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
)
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
)
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.core.publishing import ConnectorPublishingStore

from .inventory_models import (
    PersonalConnectorQuery,
    PersonalConnectorSelection,
    PersonalConnectorSelections,
    PersonalConnectorUnavailable,
    SetPersonalConnectorEnablement,
    VerifiedGroupMembership,
)
from .models import Authorized, PersonalConnection
from .service import PersonalConnectionService


class PersonalConnectorInventoryService:
    def __init__(
        self,
        definitions: ConnectorDefinitionStore,
        publishing: ConnectorPublishingStore,
        permissions: GroupPermissionReader,
        groups: VerifiedGroupMembership,
        connections: PersonalConnectionService,
        descriptions: ConnectorCapabilityDescriptionOverrideStore,
    ) -> None:
        self._definitions = definitions
        self._publishing = publishing
        self._permissions = permissions
        self._groups = groups
        self._connections = connections
        self._descriptions = descriptions

    async def _granted_connectors(self) -> frozenset[str]:
        connector_ids: set[str] = set()
        for group_id in self._groups.group_ids:
            grants = await self._permissions.list_group_permissions(group_id)
            connector_ids.update(grants.connector_ids)
        return frozenset(connector_ids)

    async def _is_eligible(self, connector_id: str) -> bool:
        return (
            connector_id in await self._granted_connectors()
            and await self._publishing.is_published(connector_id)
        )

    async def _personal_definition(self, connector_id: str) -> OAuthConnectorDefinition:
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if (
            not isinstance(result, ConnectorDefinitionFound)
            or not isinstance(result.definition, OAuthConnectorDefinition)
            or result.definition.authorization_mode != "personal"
        ):
            raise PersonalConnectorUnavailable()
        return result.definition

    async def _project(self, definition: OAuthConnectorDefinition) -> PersonalConnectorSelection:
        connection = await self._connections.get(definition.connector_id)
        override = await self._descriptions.get(ConnectorCapabilityDescriptionKey(
            kind="downstream_mcp", connector_id=definition.connector_id
        ))
        description = (
            override.description
            if isinstance(override, OverriddenCapabilityDescription)
            else definition.capability_description
        )
        return PersonalConnectorSelection(
            connector_id=definition.connector_id,
            display_name=definition.display_name,
            capability_description=description,
            enabled=connection.enabled,
            has_authorization=isinstance(connection.authorization, Authorized),
        )

    async def list(self) -> PersonalConnectorSelections:
        grants = await self._granted_connectors()
        selected: list[PersonalConnectorSelection] = []
        definitions = (await self._definitions.list()).definitions
        for definition in sorted(definitions, key=lambda item: item.connector_id):
            if (
                isinstance(definition, OAuthConnectorDefinition)
                and definition.authorization_mode == "personal"
                and definition.connector_id in grants
                and await self._publishing.is_published(definition.connector_id)
            ):
                selected.append(await self._project(definition))
        return PersonalConnectorSelections(connectors=tuple(selected))

    async def get(self, query: PersonalConnectorQuery) -> PersonalConnectorSelection:
        definition = await self._personal_definition(query.connector_id)
        if not await self._is_eligible(query.connector_id):
            raise PersonalConnectorUnavailable()
        return await self._project(definition)

    async def _require_cleanup_access(self, connector_id: str) -> None:
        if await self._is_eligible(connector_id):
            return
        if not isinstance(await self._connections.get(connector_id), PersonalConnection):
            raise PersonalConnectorUnavailable()

    async def set_enabled(
        self, command: SetPersonalConnectorEnablement
    ) -> PersonalConnectorSelection:
        definition = await self._personal_definition(command.connector_id)
        if command.enabled:
            if not await self._is_eligible(command.connector_id):
                raise PersonalConnectorUnavailable()
        else:
            await self._require_cleanup_access(command.connector_id)
        await self._connections.set_enabled(command.connector_id, command.enabled)
        return await self._project(definition)

    async def disconnect(self, query: PersonalConnectorQuery) -> None:
        await self._personal_definition(query.connector_id)
        await self._require_cleanup_access(query.connector_id)
        await self._connections.disconnect(query.connector_id)
