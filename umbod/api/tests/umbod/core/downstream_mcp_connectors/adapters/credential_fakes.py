from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.models import CredentialState, OAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    CredentialFound,
    CredentialMissing,
    SaveCredential,
)


class MemoryCredentialStore:
    def __init__(self) -> None:
        self.credentials: dict[str, CredentialState] = {}
        self.reads = 0
        self.writes = 0

    async def get(self, query: ConnectorIdQuery) -> CredentialFound | CredentialMissing:
        self.reads += 1
        credential = self.credentials.get(query.connector_id)
        if credential is None:
            return CredentialMissing(connector_id=query.connector_id)
        return CredentialFound(credential=credential)

    async def save(self, command: SaveCredential) -> CredentialFound:
        self.writes += 1
        self.credentials[command.credential.connector_id] = command.credential
        return CredentialFound(credential=command.credential)

    async def delete(self, command: ConnectorIdQuery) -> CredentialFound | CredentialMissing:
        self.writes += 1
        credential = self.credentials.pop(command.connector_id, None)
        if credential is None:
            return CredentialMissing(connector_id=command.connector_id)
        return CredentialFound(credential=credential)

    async def replace_oauth_authorization(
        self, connector_id: str, expected: SecretStr, replacement: SecretStr
    ) -> bool:
        self.writes += 1
        credential = self.credentials.get(connector_id)
        if not isinstance(credential, OAuthCredentialState):
            return False
        if credential.authorization.get_secret_value() != expected.get_secret_value():
            return False
        self.credentials[connector_id] = OAuthCredentialState(
            connector_id=connector_id, authorization=replacement
        )
        return True
