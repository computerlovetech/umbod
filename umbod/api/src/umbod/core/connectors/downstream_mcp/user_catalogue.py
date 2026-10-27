from datetime import datetime
from collections.abc import Callable

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema, CapabilityIdentity, CapabilityNotFoundError,
    NormalizedCapability, PresentCapabilityOutputSchema,
)
from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.capabilities.catalog import CapabilityCatalog, InMemoryCapabilityCatalog
from umbod.core.connectors.downstream_mcp.catalog.capability_catalog import DownstreamCapabilityRecord
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinitionModel, uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections import (
    CanonicalPrincipal, PersonalConnectionKey, PersonalConnectorInventory,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery
from umbod.core.connectors.downstream_mcp.personal_tools.ports import PersonalToolAccessStore
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, CredentialFound, EncryptedCredentialStore
from umbod.core.user_catalogue import CatalogueConnector, CatalogueToolCapability


class SharedDownstreamCatalogue:
    def __init__(self, records: tuple[DownstreamCapabilityRecord, ...]) -> None:
        self._catalog = InMemoryCapabilityCatalog(tuple(
            record.capability.model_copy(update={
                "connector_capability_description": record.definition.capability_description,
            })
            for record in records
            if not uses_personal_oauth(record.definition)
        ))

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        return await self._catalog.list_capabilities()

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        return await self._catalog.resolve(identity)


class SharedDownstreamReadiness:
    def __init__(self, catalog: CapabilityCatalog, credentials: EncryptedCredentialStore) -> None:
        self._catalog = catalog
        self._credentials = credentials
        self._credential_readiness: dict[str, bool] = {}

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        try:
            await self._catalog.resolve(identity)
        except CapabilityNotFoundError:
            return False
        if identity.connector_id not in self._credential_readiness:
            self._credential_readiness[identity.connector_id] = isinstance(
                await self._credentials.get(ConnectorIdQuery(connector_id=identity.connector_id)),
                CredentialFound,
            )
        return self._credential_readiness[identity.connector_id]


class PersonalCatalogueSource:
    def __init__(
        self, inventory: PersonalConnectorInventory, access: PersonalToolAccessStore,
        principal: CanonicalPrincipal, groups: tuple[str, ...], runtime_enabled: bool,
        clock: Callable[[], datetime],
    ) -> None:
        self._inventory = inventory
        self._access = access
        self._principal = principal
        self._groups = groups
        self._runtime_enabled = runtime_enabled
        self._clock = clock

    async def list_connectors(self) -> tuple[CatalogueConnector, ...]:
        connectors: list[CatalogueConnector] = []
        for selection in (await self._inventory.list()).connectors:
            tools = await self._access.list_available(PersonalRuntimeAuthorizationQuery(
                key=PersonalConnectionKey(principal=self._principal, connector_id=selection.connector_id),
                group_ids=self._groups, now=self._clock(),
            )) if self._runtime_enabled else ()
            connectors.append(CatalogueConnector(
                connector_id=selection.connector_id, kind="downstream_mcp",
                display_name=selection.display_name,
                capability_description=selection.capability_description, ownership="personal",
                capabilities=tuple(CatalogueToolCapability(
                    kind="tool", key=record.tool.identity.downstream_name,
                    name=record.tool.title, description=record.tool.description,
                    input_schema=record.tool.input_schema,
                    output_schema=(
                        PresentCapabilityOutputSchema(schema=record.tool.output_schema)
                        if record.tool.output_schema_status == "present"
                        else AbsentCapabilityOutputSchema()
                    ),
                ) for record in tools),
            ))
        return tuple(connectors)


class PersonalNamespace:
    def __init__(self, definitions: tuple[ConnectorDefinitionModel, ...]) -> None:
        self._stems = tuple(
            (definition.connector_id, mangle_public_tool_name(
                definition.tool_name_prefix, "UmbodPersonalNamespaceSentinel",
            ).removesuffix("UmbodPersonalNamespaceSentinel"))
            for definition in definitions if uses_personal_oauth(definition)
        )

    def allows(self, name: str, connector_id: str, personal: bool) -> bool:
        if any(not stem for _, stem in self._stems):
            return False
        owners = tuple(
            owner for owner, stem in self._stems
            if not stem or name == stem.rstrip("_") or name.startswith(stem)
        )
        return owners == (connector_id,) if personal else not owners
