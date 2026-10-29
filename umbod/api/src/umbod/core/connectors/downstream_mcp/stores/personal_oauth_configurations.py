import json
from uuid import uuid4

from pydantic import SecretStr

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections.models import PersonalConnection, Unauthorized
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    PersonalOAuthConfiguration, PersonalOAuthConfigurationConflict,
    PersonalOAuthConfigurationQuery, PersonalOAuthConfigurationUnavailable,
    PersonalOAuthPolicy, PersonalOAuthSettings, PreconfiguredConfidentialOAuthClient,
    ReplacePersonalOAuthConfiguration, legacy_personal_oauth_policy,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configuration_schema import (
    PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, PERSONAL_OAUTH_CONFIGURATION_TABLE,
    PersonalOAuthConfigurationKey, PersonalOAuthConfigurationRecord,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID, PERSONAL_OAUTH_ATTEMPT_TABLE
from umbod.core.connectors.downstream_mcp.stores.ports import CONNECTOR_DEFINITION_ADAPTER
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE,
    PERSONAL_CONNECTION_CONNECTOR_ID, PERSONAL_CONNECTION_TABLE,
    PersonalConnectionRecord, PersonalConnectionRecordKey,
)
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.persistence import AllFields, Database, DatabaseSession, DeleteQuery, Equals, Query, TransactionMode, Unordered, UpsertCommand


def _serialize_secret(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    raise TypeError("Unsupported OAuth configuration value")


async def load_personal_oauth_configuration(
    session: DatabaseSession, cipher: TextCipher, connector_id: str
) -> PersonalOAuthConfiguration:
    definition = await session.find_one(
        CONNECTOR_DEFINITION_TABLE,
        Query(filter=Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, connector_id), projection=AllFields(), ordering=Unordered()),
    )
    if definition is None:
        raise PersonalOAuthConfigurationUnavailable("Personal OAuth configuration unavailable")
    try:
        personal = uses_personal_oauth(CONNECTOR_DEFINITION_ADAPTER.validate_python(definition.document))
    except Exception:
        raise PersonalOAuthConfigurationUnavailable("Personal OAuth configuration unavailable") from None
    if not personal:
        raise PersonalOAuthConfigurationUnavailable("Personal OAuth configuration unavailable")
    row = await session.find_one(
        PERSONAL_OAUTH_CONFIGURATION_TABLE,
        Query(filter=Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, connector_id), projection=AllFields(), ordering=Unordered()),
    )
    if row is None:
        return PersonalOAuthConfiguration(connector_id=connector_id, policy=legacy_personal_oauth_policy())
    try:
        configuration = PersonalOAuthConfiguration.model_validate_json(cipher.decrypt(row.document))
        if configuration.connector_id != connector_id or configuration.policy.revision != row.revision or row.connector_id != connector_id:
            raise ValueError("Invalid binding")
        return configuration
    except Exception:
        raise PersonalOAuthConfigurationUnavailable("Personal OAuth configuration unavailable") from None


async def install_personal_oauth_configuration(
    session: DatabaseSession, cipher: TextCipher, connector_id: str, settings: PersonalOAuthSettings
) -> PersonalOAuthConfiguration:
    configuration = PersonalOAuthConfiguration(
        connector_id=connector_id,
        policy=PersonalOAuthPolicy(revision=uuid4().hex, requested_scopes=settings.requested_scopes, client=settings.client),
    )
    await session.upsert(
        PERSONAL_OAUTH_CONFIGURATION_TABLE,
        UpsertCommand(
            key=PersonalOAuthConfigurationKey(connector_id=connector_id),
            row=PersonalOAuthConfigurationRecord(
                connector_id=connector_id, revision=configuration.policy.revision,
                document=cipher.encrypt(json.dumps(configuration.model_dump(mode="python"), default=_serialize_secret)),
            ),
        ),
    )
    return configuration


async def _invalidate_connections(session: DatabaseSession, cipher: TextCipher, connector_id: str) -> None:
    rows = await session.find_many(
        PERSONAL_CONNECTION_TABLE,
        Query(filter=Equals(PERSONAL_CONNECTION_CONNECTOR_ID, connector_id), projection=AllFields(), ordering=Unordered()),
    )
    for row in rows:
        try:
            current = PersonalConnection.model_validate_json(cipher.decrypt(row.document))
            if (current.key.principal.namespace, current.key.principal.subject, current.key.connector_id) != (row.namespace, row.subject, connector_id):
                raise ValueError("Invalid binding")
        except Exception:
            raise PersonalOAuthConfigurationUnavailable("Personal OAuth configuration unavailable") from None
        replacement = PersonalConnection(key=current.key, enabled=current.enabled, authorization=Unauthorized(), revision=uuid4().hex)
        await session.upsert(
            PERSONAL_CONNECTION_TABLE,
            UpsertCommand(
                key=PersonalConnectionRecordKey(namespace=row.namespace, subject=row.subject, connector_id=connector_id),
                row=PersonalConnectionRecord(namespace=row.namespace, subject=row.subject, connector_id=connector_id, document=cipher.encrypt(replacement.model_dump_json())),
            ),
        )


class EncryptedPersonalOAuthConfigurationStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            removed = await session.delete(
                PERSONAL_OAUTH_CONFIGURATION_TABLE,
                DeleteQuery(Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, connector_id)),
            )
            if removed:
                await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", connector_id))

    async def get(self, query: PersonalOAuthConfigurationQuery) -> PersonalOAuthConfiguration:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await load_personal_oauth_configuration(session, self._cipher, query.connector_id)

    async def replace(self, command: ReplacePersonalOAuthConfiguration) -> PersonalOAuthConfiguration:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            current = await load_personal_oauth_configuration(session, self._cipher, command.connector_id)
            if current.policy.revision != command.expected_revision:
                raise PersonalOAuthConfigurationConflict("Personal OAuth configuration revision conflict")
            if not isinstance(command.settings.client, PreconfiguredConfidentialOAuthClient) and (
                command.settings.requested_scopes == current.policy.requested_scopes and command.settings.client == current.policy.client
            ):
                return current
            await session.delete(PERSONAL_OAUTH_ATTEMPT_TABLE, DeleteQuery(Equals(PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID, command.connector_id)))
            await _invalidate_connections(session, self._cipher, command.connector_id)
            configuration = await install_personal_oauth_configuration(session, self._cipher, command.connector_id, command.settings)
            await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", command.connector_id))
            return configuration
