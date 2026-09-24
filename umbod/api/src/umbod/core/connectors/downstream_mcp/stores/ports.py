from typing import Literal, Protocol

from pydantic import SecretStr, TypeAdapter

from umbod.core.connectors.downstream_mcp.models import (
    CatalogReconciliation,
    ConnectorDefinition,
    ConnectorHealth,
    CredentialState,
    DomainModel,
    NonEmptyString,
    ToolCatalogSnapshot,
)


CONNECTOR_DEFINITION_ADAPTER = TypeAdapter(ConnectorDefinition)
CREDENTIAL_STATE_ADAPTER = TypeAdapter(CredentialState)


class ConnectorIdQuery(DomainModel):
    connector_id: NonEmptyString


class PublicPathQuery(DomainModel):
    public_path: NonEmptyString


class SaveConnectorDefinition(DomainModel):
    definition: ConnectorDefinition


class ConnectorDefinitionFound(DomainModel):
    found: Literal[True] = True
    definition: ConnectorDefinition


class ConnectorDefinitionMissing(DomainModel):
    found: Literal[False] = False
    connector_id: NonEmptyString


class ConnectorDefinitionList(DomainModel):
    definitions: tuple[ConnectorDefinition, ...]


class SaveCredential(DomainModel):
    credential: CredentialState


class CredentialFound(DomainModel):
    found: Literal[True] = True
    credential: CredentialState


class CredentialMissing(DomainModel):
    found: Literal[False] = False
    connector_id: NonEmptyString


class ReplaceToolCatalog(DomainModel):
    snapshot: ToolCatalogSnapshot


class SaveConnectorHealth(DomainModel):
    health: ConnectorHealth


class ToolCatalogFound(DomainModel):
    found: Literal[True] = True
    snapshot: ToolCatalogSnapshot


class ToolCatalogMissing(DomainModel):
    found: Literal[False] = False
    connector_id: NonEmptyString


class ConnectorHealthFound(DomainModel):
    found: Literal[True] = True
    health: ConnectorHealth


class ConnectorHealthMissing(DomainModel):
    found: Literal[False] = False
    connector_id: NonEmptyString


class ConnectorDefinitionStore(Protocol):
    async def save(self, command: SaveConnectorDefinition) -> ConnectorDefinitionFound: ...

    async def get(
        self, query: ConnectorIdQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing: ...

    async def list(self) -> ConnectorDefinitionList: ...

    async def get_by_public_path(
        self, query: PublicPathQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing: ...

    async def delete(
        self, command: ConnectorIdQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing: ...


class EncryptedCredentialStore(Protocol):
    async def replace_oauth_authorization(
        self, connector_id: str, expected: SecretStr, replacement: SecretStr
    ) -> bool: ...

    async def save(self, command: SaveCredential) -> CredentialFound: ...

    async def get(self, query: ConnectorIdQuery) -> CredentialFound | CredentialMissing: ...

    async def delete(self, command: ConnectorIdQuery) -> CredentialFound | CredentialMissing: ...


class ToolCatalogStore(Protocol):
    async def replace(self, command: ReplaceToolCatalog) -> CatalogReconciliation: ...

    async def get(self, query: ConnectorIdQuery) -> ToolCatalogFound | ToolCatalogMissing: ...

    async def delete(self, command: ConnectorIdQuery) -> ToolCatalogFound | ToolCatalogMissing: ...


class ConnectorHealthStore(Protocol):
    async def save(self, command: SaveConnectorHealth) -> ConnectorHealthFound: ...

    async def get(self, query: ConnectorIdQuery) -> ConnectorHealthFound | ConnectorHealthMissing: ...

    async def delete(self, command: ConnectorIdQuery) -> ConnectorHealthFound | ConnectorHealthMissing: ...
