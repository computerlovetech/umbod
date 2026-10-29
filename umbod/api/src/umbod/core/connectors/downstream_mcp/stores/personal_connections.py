from .personal_discovery_projection import update_personal_discovery
from . import personal_connection_records

import json

from .personal_discovery_schema import PERSONAL_DISCOVERY_TABLE, PERSONAL_DISCOVERY_CONNECTOR_ID

from .personal_refresh_records import clear_refresh
from .personal_refresh_schema import PERSONAL_REFRESH_TABLE, PERSONAL_REFRESH_CONNECTOR_ID

from .personal_authorization_health_schema import (
    PERSONAL_AUTHORIZATION_REJECTION_TABLE,
    PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE,
    PERSONAL_AUTHORIZATION_REJECTION_SUBJECT,
    PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID,
)
from collections.abc import Callable

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_models import (
    PersonalConnectorUnavailable,
)
from umbod.core.connectors.downstream_mcp.stores.ports import CONNECTOR_DEFINITION_ADAPTER
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    Authorized,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionState,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
    disconnected,
    replace_authorization,
    set_enabled,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_TABLE,
    PERSONAL_CONNECTION_CONNECTOR_ID,
    PERSONAL_CONNECTION_TABLE,
    PersonalConnectionRecord,
    PersonalConnectionRecordKey,
)
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


class EncryptedPersonalConnectionStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def _get(
        self, session: DatabaseSession, key: PersonalConnectionKey
    ) -> PersonalConnectionState:
        return await personal_connection_records.load_personal_connection(session, self._cipher, key)

    async def get(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await self._get(session, key)

    async def _validate_target(
        self, session: DatabaseSession, key: PersonalConnectionKey
    ) -> None:
        return None

    async def _mutate(
        self,
        key: PersonalConnectionKey,
        transition: Callable[[PersonalConnectionState], PersonalConnectionState],
    ) -> PersonalConnectionState:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            await self._validate_target(session, key)
            current = await self._get(session, key)
            state = transition(current)
            if transition is disconnected:
                await clear_refresh(session, key)
                await session.delete(PERSONAL_AUTHORIZATION_REJECTION_TABLE, DeleteQuery(AllOf((
                    Equals(PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE, key.principal.namespace),
                    Equals(PERSONAL_AUTHORIZATION_REJECTION_SUBJECT, key.principal.subject),
                    Equals(PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID, key.connector_id),
                ))))
            if isinstance(state, PersonalConnection) and state != current:
                payload = state.model_dump(mode="json")
                if isinstance(state.authorization, Authorized):
                    payload["authorization"]["authorization"] = (
                        state.authorization.authorization.get_secret_value()
                    )
                await session.upsert(
                    PERSONAL_CONNECTION_TABLE,
                    UpsertCommand(
                        key=PersonalConnectionRecordKey(
                            namespace=key.principal.namespace,
                            subject=key.principal.subject,
                            connector_id=key.connector_id,
                        ),
                        row=PersonalConnectionRecord(
                            namespace=key.principal.namespace,
                            subject=key.principal.subject,
                            connector_id=key.connector_id,
                            document=self._cipher.encrypt(json.dumps(payload)),
                        ),
                    ),
                )
                await update_personal_discovery(session, self._cipher, key)
                await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", key.connector_id))
            return state

    async def set_enabled(
        self, command: SetPersonalConnectionEnabled
    ) -> PersonalConnectionState:
        return await self._mutate(
            command.key, lambda state: set_enabled(state, command.enabled)
        )

    async def disconnect(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        return await self._mutate(key, disconnected)

    async def replace_authorization(
        self, command: ReplacePersonalAuthorization
    ) -> PersonalConnectionState:
        return await self._mutate(
            command.key, lambda state: replace_authorization(state, command)
        )

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            removed = await session.delete(
                PERSONAL_CONNECTION_TABLE,
                DeleteQuery(Equals(PERSONAL_CONNECTION_CONNECTOR_ID, connector_id)),
            )
            removed += await session.delete(PERSONAL_AUTHORIZATION_REJECTION_TABLE, DeleteQuery(Equals(PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID, connector_id)))
            removed += await session.delete(PERSONAL_REFRESH_TABLE, DeleteQuery(Equals(PERSONAL_REFRESH_CONNECTOR_ID, connector_id)))
            await session.delete(PERSONAL_DISCOVERY_TABLE, DeleteQuery(Equals(PERSONAL_DISCOVERY_CONNECTOR_ID, connector_id)))
            if removed:
                await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", connector_id))


class DefinitionBoundPersonalConnectionStore(EncryptedPersonalConnectionStore):
    async def _validate_target(
        self, session: DatabaseSession, key: PersonalConnectionKey
    ) -> None:
        row = await session.find_one(
            CONNECTOR_DEFINITION_TABLE,
            Query(
                filter=Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, key.connector_id),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if row is None:
            raise PersonalConnectorUnavailable()
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
        if not uses_personal_oauth(definition):
            raise PersonalConnectorUnavailable()
