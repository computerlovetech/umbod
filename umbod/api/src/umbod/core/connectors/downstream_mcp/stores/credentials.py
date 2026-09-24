import json
from pydantic import SecretStr

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.models import OAuthCredentialState, StaticBearerCredentialState
from umbod.core.connectors.downstream_mcp.stores.ports import (
    CREDENTIAL_STATE_ADAPTER,
    ConnectorIdQuery,
    CredentialFound,
    CredentialMissing,
    SaveCredential,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_CREDENTIAL_CONNECTOR_ID,
    ConnectorCredentialKey,
    ConnectorCredentialRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


async def save_credential(
    session: DatabaseSession,
    table: Table[ConnectorCredentialRecord, ConnectorCredentialKey],
    cipher: TextCipher,
    command: SaveCredential,
) -> CredentialFound:
    credential = CREDENTIAL_STATE_ADAPTER.validate_python(command.credential)
    payload = credential.model_dump(mode="json")
    if isinstance(credential, StaticBearerCredentialState):
        payload["bearer_token"] = credential.bearer_token.get_secret_value()
    if isinstance(credential, OAuthCredentialState):
        payload["authorization"] = credential.authorization.get_secret_value()
    await session.upsert(
        table,
        UpsertCommand(
            key=ConnectorCredentialKey(connector_id=credential.connector_id),
            row=ConnectorCredentialRecord(
                connector_id=credential.connector_id,
                document=cipher.encrypt(json.dumps(payload)),
            ),
        ),
    )
    return CredentialFound(credential=credential)


async def find_credential_record(
    session: DatabaseSession,
    table: Table[ConnectorCredentialRecord, ConnectorCredentialKey],
    connector_id: str,
) -> ConnectorCredentialRecord | None:
    return await session.find_one(
        table,
        Query(
            filter=Equals(CONNECTOR_CREDENTIAL_CONNECTOR_ID, connector_id),
            projection=AllFields(),
            ordering=Unordered(),
        ),
    )


class EncryptedCredentialStoreService:
    def __init__(
        self,
        database: Database,
        table: Table[ConnectorCredentialRecord, ConnectorCredentialKey],
        cipher: TextCipher,
    ) -> None:
        self._database = database
        self._table = table
        self._cipher = cipher

    async def save(self, command: SaveCredential) -> CredentialFound:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await save_credential(session, self._table, self._cipher, command)

    async def replace_oauth_authorization(
        self, connector_id: str, expected: SecretStr, replacement: SecretStr
    ) -> bool:
        # Never resurrect a deleted connection or overwrite a newer authorization.
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await find_credential_record(session, self._table, connector_id)
            if row is None:
                return False
            current = CREDENTIAL_STATE_ADAPTER.validate_json(self._cipher.decrypt(row.document))
            if not isinstance(current, OAuthCredentialState) or current.authorization != expected:
                return False
            await save_credential(session, self._table, self._cipher, SaveCredential(
                credential=OAuthCredentialState(connector_id=connector_id, authorization=replacement)
            ))
            return True

    async def get(self, query: ConnectorIdQuery) -> CredentialFound | CredentialMissing:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await find_credential_record(session, self._table, query.connector_id)
        if row is None:
            return CredentialMissing(connector_id=query.connector_id)
        return CredentialFound(
            credential=CREDENTIAL_STATE_ADAPTER.validate_json(self._cipher.decrypt(row.document))
        )

    async def delete(self, command: ConnectorIdQuery) -> CredentialFound | CredentialMissing:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await find_credential_record(session, self._table, command.connector_id)
            await session.delete(
                self._table,
                DeleteQuery(Equals(CONNECTOR_CREDENTIAL_CONNECTOR_ID, command.connector_id)),
            )
        if row is None:
            return CredentialMissing(connector_id=command.connector_id)
        return CredentialFound(
            credential=CREDENTIAL_STATE_ADAPTER.validate_json(self._cipher.decrypt(row.document))
        )
