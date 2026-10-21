from umbod.core.capabilities import CapabilityAvailability, CapabilityIdentity
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
)

from .models import SharedRuntimeConnection
from .ports import DownstreamRuntimeUnavailable


class SharedDownstreamRuntimeResolver:
    def __init__(
        self,
        availability: CapabilityAvailability,
        definitions: ConnectorDefinitionStore,
        credentials: EncryptedCredentialStore,
    ) -> None:
        self._availability = availability
        self._definitions = definitions
        self._credentials = credentials

    async def resolve(self, identity: CapabilityIdentity) -> SharedRuntimeConnection:
        if identity.connector_kind != "downstream_mcp" or not await self._availability.is_available(identity):
            raise DownstreamRuntimeUnavailable("Downstream capability is not available")
        query = ConnectorIdQuery(connector_id=identity.connector_id)
        definition = await self._definitions.get(query)
        if not isinstance(definition, ConnectorDefinitionFound) or uses_personal_oauth(definition.definition):
            raise DownstreamRuntimeUnavailable("Downstream capability is not available")
        credential = await self._credentials.get(query)
        if not isinstance(credential, CredentialFound):
            raise DownstreamRuntimeUnavailable("Downstream capability is not available")
        return SharedRuntimeConnection(command=DiscoverDownstreamTools(
            definition=definition.definition, credential=credential.credential
        ))
