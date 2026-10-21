from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationUnavailable
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import load_personal_oauth_configuration

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, Field, SecretStr, TypeAdapter

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    PersonalConnection,
    PersonalConnectionKey,
    ReplacePersonalAuthorization,
    replace_authorization,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    ClaimPersonalOAuthAttempt,
    ClaimedPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    FailPersonalOAuthAttempt,
    PersonalOAuthAttemptQuery,
    PersonalOAuthAttemptView,
    PersonalOAuthConflict,
    PersonalOAuthModel,
    PersonalOAuthUnavailable,
    PreparedPersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from umbod.core.connectors.downstream_mcp.stores.personal_connections import (
    EncryptedPersonalConnectionStore,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import (
    PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID,
    PERSONAL_OAUTH_ATTEMPT_ID,
    PERSONAL_OAUTH_ATTEMPT_NAMESPACE,
    PERSONAL_OAUTH_ATTEMPT_SUBJECT,
    PERSONAL_OAUTH_ATTEMPT_TABLE,
    PersonalOAuthAttemptKey,
    PersonalOAuthAttemptRecord,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    CONNECTOR_DEFINITION_ADAPTER,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_TABLE,
    PERSONAL_CONNECTION_TABLE,
    PersonalConnectionRecord,
    PersonalConnectionRecordKey,
)
from umbod.core.permissions.stores.schema import (
    CONNECTOR_PERMISSION_CONNECTOR_ID,
    CONNECTOR_PERMISSION_GROUP_ID,
    CONNECTOR_PERMISSION_TABLE,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    OneOf,
    Query,
    Predicate,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
)


class AttemptMetadata(PersonalOAuthModel):
    key: PersonalConnectionKey
    attempt_id: str
    expires_at: AwareDatetime


class PreparingAttempt(AttemptMetadata):
    status: Literal["preparing"]
    reservation: ReservePersonalOAuthAttempt


class PendingAttempt(AttemptMetadata):
    status: Literal["pending"]
    reservation: ReservePersonalOAuthAttempt
    prepared: PreparedPersonalOAuth


class ExchangingAttempt(AttemptMetadata):
    status: Literal["exchanging"]
    reservation: ReservePersonalOAuthAttempt
    prepared: PreparedPersonalOAuth
    claim_id: str


class TerminalAttempt(AttemptMetadata):
    status: Literal["completed", "cancelled", "failed", "expired"]


ActiveAttempt = PreparingAttempt | PendingAttempt | ExchangingAttempt
Attempt = Annotated[ActiveAttempt | TerminalAttempt, Field(discriminator="status")]
_ATTEMPT_ADAPTER = TypeAdapter(Attempt)


def _serialize(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Unsupported encrypted document value")


RowT = TypeVar("RowT", bound=BaseModel)


def _query(predicate: Predicate[RowT]) -> Query[RowT, RowT]:
    return Query(filter=predicate, projection=AllFields(), ordering=Unordered())


def _terminal(
    attempt: AttemptMetadata,
    status: Literal["completed", "cancelled", "failed", "expired"],
) -> TerminalAttempt:
    return TerminalAttempt(
        key=attempt.key,
        attempt_id=attempt.attempt_id,
        expires_at=attempt.expires_at,
        status=status,
    )


def _view(attempt: Attempt) -> PersonalOAuthAttemptView:
    return PersonalOAuthAttemptView(
        attempt_id=attempt.attempt_id,
        status=attempt.status,
        expires_at=attempt.expires_at,
    )


class ExpiredPersonalOAuthAttempt(Exception):
    def __init__(self, attempt: ActiveAttempt) -> None:
        super().__init__("Personal OAuth attempt expired")
        self.attempt = attempt


class EncryptedPersonalOAuthAttemptStore:
    def __init__(
        self, database: Database, cipher: TextCipher, clock: Callable[[], datetime]
    ) -> None:
        self._database = database
        self._cipher = cipher
        self._clock = clock
        self._connections = EncryptedPersonalConnectionStore(database, cipher)

    def _decode(self, row: PersonalOAuthAttemptRecord) -> Attempt:
        attempt = _ATTEMPT_ADAPTER.validate_json(self._cipher.decrypt(row.document))
        expected = (
            attempt.attempt_id,
            attempt.key.principal.namespace,
            attempt.key.principal.subject,
            attempt.key.connector_id,
        )
        actual = (row.attempt_id, row.namespace, row.subject, row.connector_id)
        if expected != actual:
            raise PersonalOAuthUnavailable()
        if not isinstance(attempt, TerminalAttempt) and (
            attempt.reservation.key != attempt.key
            or attempt.reservation.attempt_id != attempt.attempt_id
            or attempt.reservation.expires_at != attempt.expires_at
        ):
            raise PersonalOAuthUnavailable()
        return attempt

    async def _save(self, session: DatabaseSession, attempt: Attempt) -> None:
        await session.upsert(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            UpsertCommand(
                key=PersonalOAuthAttemptKey(attempt_id=attempt.attempt_id),
                row=PersonalOAuthAttemptRecord(
                    attempt_id=attempt.attempt_id,
                    namespace=attempt.key.principal.namespace,
                    subject=attempt.key.principal.subject,
                    connector_id=attempt.key.connector_id,
                    document=self._cipher.encrypt(
                        json.dumps(
                            attempt.model_dump(mode="python"), default=_serialize
                        )
                    ),
                ),
            ),
        )

    @asynccontextmanager
    async def _transition_session(self) -> AsyncIterator[DatabaseSession]:
        expired = False
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            try:
                yield session
            except ExpiredPersonalOAuthAttempt as error:
                await self._save(session, _terminal(error.attempt, "expired"))
                expired = True
        if expired:
            raise PersonalOAuthUnavailable()

    def _require_unexpired(self, attempt: ActiveAttempt, now: datetime) -> None:
        if max(now, self._clock()) >= attempt.expires_at:
            raise ExpiredPersonalOAuthAttempt(attempt)

    async def _load_raw(self, session: DatabaseSession, attempt_id: str) -> Attempt:
        row = await session.find_one(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            _query(Equals(PERSONAL_OAUTH_ATTEMPT_ID, attempt_id)),
        )
        if row is None:
            raise PersonalOAuthUnavailable()
        return self._decode(row)

    async def _owned_raw(
        self, session: DatabaseSession, query: PersonalOAuthAttemptQuery
    ) -> Attempt:
        attempt = await self._load_raw(session, query.attempt_id)
        if attempt.key != query.key:
            raise PersonalOAuthUnavailable()
        return attempt

    async def _owned(
        self, session: DatabaseSession, query: PersonalOAuthAttemptQuery
    ) -> Attempt:
        attempt = await self._owned_raw(session, query)
        if (
            not isinstance(attempt, TerminalAttempt)
            and max(query.now, self._clock()) >= attempt.expires_at
        ):
            attempt = _terminal(attempt, "expired")
            await self._save(session, attempt)
        return attempt

    async def _eligible(
        self, session: DatabaseSession, command: ReservePersonalOAuthAttempt
    ) -> PersonalConnection:
        definition_row = await session.find_one(
            CONNECTOR_DEFINITION_TABLE,
            _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, command.key.connector_id)),
        )
        if definition_row is None:
            raise PersonalOAuthUnavailable()
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(
            definition_row.document
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                definition.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            not uses_personal_oauth(definition)
            or fingerprint != command.definition_fingerprint
            or definition.endpoint_url != command.endpoint_url
        ):
            raise PersonalOAuthUnavailable()
        try:
            configuration = await load_personal_oauth_configuration(session, self._cipher, command.key.connector_id)
        except PersonalOAuthConfigurationUnavailable:
            raise PersonalOAuthUnavailable() from None
        if configuration.policy != command.preparation.policy:
            raise PersonalOAuthUnavailable()
        connection = await self._connections._get(session, command.key)
        if (
            not isinstance(connection, PersonalConnection)
            or not connection.enabled
            or connection.revision != command.expected_revision
        ):
            raise PersonalOAuthUnavailable()
        publication = await session.find_one(
            PUBLICATION_STATE_TABLE,
            _query(Equals(PUBLICATION_STATE_CONNECTOR_ID, command.key.connector_id)),
        )
        if publication is None or not publication.published or not command.group_ids:
            raise PersonalOAuthUnavailable()
        grant = await session.find_one(
            CONNECTOR_PERMISSION_TABLE,
            _query(
                AllOf(
                    (
                        Equals(
                            CONNECTOR_PERMISSION_CONNECTOR_ID, command.key.connector_id
                        ),
                        OneOf(CONNECTOR_PERMISSION_GROUP_ID, command.group_ids),
                    )
                )
            ),
        )
        if grant is None:
            raise PersonalOAuthUnavailable()
        return connection

    async def reserve(
        self, command: ReservePersonalOAuthAttempt
    ) -> PersonalOAuthAttemptView:
        state_secret = command.preparation.state
        state = state_secret.get_secret_value()
        if (
            command.expires_at <= command.created_at
            or command.preparation.endpoint_url != command.endpoint_url
            or not state.startswith(command.attempt_id + ".")
            or len(state) <= len(command.attempt_id) + 1
        ):
            raise PersonalOAuthUnavailable()
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            now = max(command.created_at, self._clock())
            if command.expires_at <= now:
                raise PersonalOAuthUnavailable()
            await self._eligible(session, command)
            rows = await session.find_many(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                _query(
                    AllOf(
                        (
                            Equals(
                                PERSONAL_OAUTH_ATTEMPT_NAMESPACE,
                                command.key.principal.namespace,
                            ),
                            Equals(
                                PERSONAL_OAUTH_ATTEMPT_SUBJECT,
                                command.key.principal.subject,
                            ),
                            Equals(
                                PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID,
                                command.key.connector_id,
                            ),
                        )
                    )
                ),
            )
            for row in rows:
                attempt = self._decode(row)
                if (
                    not isinstance(attempt, TerminalAttempt)
                    and attempt.expires_at > now
                ):
                    raise PersonalOAuthConflict()
            duplicate = await session.find_one(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                _query(Equals(PERSONAL_OAUTH_ATTEMPT_ID, command.attempt_id)),
            )
            if duplicate is not None:
                raise PersonalOAuthConflict()
            for row in rows:
                await session.delete(
                    PERSONAL_OAUTH_ATTEMPT_TABLE,
                    DeleteQuery(Equals(PERSONAL_OAUTH_ATTEMPT_ID, row.attempt_id)),
                )
            attempt = PreparingAttempt(
                key=command.key,
                attempt_id=command.attempt_id,
                expires_at=command.expires_at,
                status="preparing",
                reservation=command,
            )
            await self._save(session, attempt)
            return _view(attempt)

    async def publish(
        self, command: PublishPersonalOAuthAttempt
    ) -> PersonalOAuthAttemptView:
        async with self._transition_session() as session:
            attempt = await self._owned_raw(session, command.query)
            if not isinstance(attempt, PreparingAttempt):
                raise PersonalOAuthUnavailable()
            self._require_unexpired(attempt, command.query.now)
            await self._eligible(session, attempt.reservation)
            self._require_unexpired(attempt, command.query.now)
            pending = PendingAttempt(
                **attempt.model_dump(exclude={"status"}),
                status="pending",
                prepared=command.prepared,
            )
            await self._save(session, pending)
            return _view(pending)

    async def get(self, query: PersonalOAuthAttemptQuery) -> PersonalOAuthAttemptView:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            return _view(await self._owned(session, query))

    async def cancel(
        self, query: PersonalOAuthAttemptQuery
    ) -> PersonalOAuthAttemptView:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            attempt = await self._owned(session, query)
            if not isinstance(attempt, TerminalAttempt):
                attempt = _terminal(attempt, "cancelled")
                await self._save(session, attempt)
            return _view(attempt)

    async def abort_preparation(self, query: PersonalOAuthAttemptQuery) -> None:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            attempt = await self._owned(session, query)
            if isinstance(attempt, PreparingAttempt):
                await self._save(session, _terminal(attempt, "failed"))

    async def claim(
        self, command: ClaimPersonalOAuthAttempt
    ) -> ClaimedPersonalOAuthAttempt:
        state_secret = command.state
        state = state_secret.get_secret_value()
        attempt_id, separator, secret = state.partition(".")
        if not separator or not secret:
            raise PersonalOAuthUnavailable()
        async with self._transition_session() as session:
            now = max(command.now, self._clock())
            attempt = await self._load_raw(session, attempt_id)
            if not isinstance(attempt, PendingAttempt):
                raise PersonalOAuthUnavailable()
            expected_state = attempt.reservation.preparation.state
            if not hmac.compare_digest(
                expected_state.get_secret_value().encode(), state.encode(),
            ):
                raise PersonalOAuthUnavailable()
            self._require_unexpired(attempt, now)
            await self._eligible(session, attempt.reservation)
            self._require_unexpired(attempt, now)
            exchanging = ExchangingAttempt(
                **attempt.model_dump(exclude={"status"}),
                status="exchanging",
                claim_id=command.claim_id,
            )
            await self._save(session, exchanging)
            return ClaimedPersonalOAuthAttempt(
                query=PersonalOAuthAttemptQuery(
                    key=attempt.key, attempt_id=attempt.attempt_id, now=now
                ),
                claim_id=command.claim_id,
                preparation=attempt.reservation.preparation,
                prepared=attempt.prepared,
            )

    async def complete(
        self, command: CompletePersonalOAuthAttempt
    ) -> PersonalOAuthAttemptView:
        async with self._transition_session() as session:
            attempt = await self._owned_raw(session, command.query)
            if (
                not isinstance(attempt, ExchangingAttempt)
                or attempt.claim_id != command.claim_id
            ):
                raise PersonalOAuthUnavailable()
            self._require_unexpired(attempt, command.query.now)
            connection = await self._eligible(session, attempt.reservation)
            replacement = replace_authorization(
                connection,
                ReplacePersonalAuthorization(
                    key=attempt.key,
                    expected_revision=attempt.reservation.expected_revision,
                    authorization=command.authorization,
                ),
            )
            self._require_unexpired(attempt, command.query.now)
            payload = replacement.model_dump(mode="json")
            payload["authorization"]["authorization"] = (
                command.authorization.authorization.get_secret_value()
            )
            await session.upsert(
                PERSONAL_CONNECTION_TABLE,
                UpsertCommand(
                    key=PersonalConnectionRecordKey(
                        namespace=attempt.key.principal.namespace,
                        subject=attempt.key.principal.subject,
                        connector_id=attempt.key.connector_id,
                    ),
                    row=PersonalConnectionRecord(
                        namespace=attempt.key.principal.namespace,
                        subject=attempt.key.principal.subject,
                        connector_id=attempt.key.connector_id,
                        document=self._cipher.encrypt(json.dumps(payload)),
                    ),
                ),
            )
            terminal = _terminal(attempt, "completed")
            await self._save(session, terminal)
            return _view(terminal)

    async def fail(self, command: FailPersonalOAuthAttempt) -> None:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            attempt = await self._owned(session, command.query)
            if (
                isinstance(attempt, ExchangingAttempt)
                and attempt.claim_id == command.claim_id
            ):
                await self._save(session, _terminal(attempt, "failed"))

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            await session.delete(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                DeleteQuery(Equals(PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID, connector_id)),
            )
