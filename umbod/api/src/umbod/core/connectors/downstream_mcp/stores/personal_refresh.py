import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import AllOf, Database, DatabaseSession, Equals, OneOf, TransactionMode, UpsertCommand
from umbod.core.permissions.stores.schema import CONNECTOR_PERMISSION_TABLE, CONNECTOR_PERMISSION_CONNECTOR_ID, CONNECTOR_PERMISSION_GROUP_ID
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE, PUBLICATION_STATE_CONNECTOR_ID

from ..models import uses_personal_oauth
from ..personal_connections.authorization_models import ExpiringPersonalToken, PersonalOAuthGrant, PresentPersonalRefreshToken
from ..personal_connections.grant_binding import validated_bound_grant
from ..personal_connections.models import Authorized, PersonalConnection, PersonalConnectionKey
from ..personal_connections.refresh_models import CompletePersonalRefresh, FailPersonalRefresh, PersonalRefreshChanged, PersonalRefreshClaim, PersonalRefreshCommand, PersonalRefreshConflict, PersonalRefreshReconnectRequired, PersonalRefreshUnsupported, ReservePersonalRefresh
from .personal_authorization_rejections import authorization_fingerprint, clear_rejection, matching_rejection
from .personal_connections import load_personal_connection
from .personal_oauth_configurations import load_personal_oauth_configuration
from .personal_oauth_schema import PERSONAL_OAUTH_ATTEMPT_TABLE, PERSONAL_OAUTH_ATTEMPT_NAMESPACE, PERSONAL_OAUTH_ATTEMPT_SUBJECT, PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID
from .personal_refresh_records import clear_refresh, load_refresh, save_refresh
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .queries import query_all
from .schema import CONNECTOR_DEFINITION_TABLE, CONNECTOR_DEFINITION_CONNECTOR_ID, PERSONAL_CONNECTION_TABLE, PersonalConnectionRecord, PersonalConnectionRecordKey


class EncryptedPersonalRefreshStore:
    def __init__(self, database: Database, cipher: TextCipher, clock: Callable[[], datetime]) -> None:
        self._database = database
        self._cipher = cipher
        self._clock = clock

    async def _capture(self, session: DatabaseSession, key: PersonalConnectionKey, groups: tuple[str, ...], now: datetime, claim_id: str, deadline: datetime) -> PersonalRefreshClaim:
        connection = await load_personal_connection(session, self._cipher, key)
        if not isinstance(connection, PersonalConnection) or not connection.enabled or not isinstance(connection.authorization, Authorized):
            raise PersonalRefreshUnsupported()
        row = await session.find_one(CONNECTOR_DEFINITION_TABLE, query_all(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, key.connector_id)))
        if row is None:
            raise PersonalRefreshChanged()
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
        if definition.connector_id != key.connector_id or not uses_personal_oauth(definition):
            raise PersonalRefreshUnsupported()
        configuration = await load_personal_oauth_configuration(session, self._cipher, key.connector_id)
        try:
            grant = validated_bound_grant(connection.authorization, key, now, definition, configuration.policy)
        except ValueError:
            raise PersonalRefreshUnsupported() from None
        if grant.client_mode == "dynamic_public" or not isinstance(grant.refresh_token, PresentPersonalRefreshToken):
            raise PersonalRefreshUnsupported()
        publication = await session.find_one(PUBLICATION_STATE_TABLE, query_all(Equals(PUBLICATION_STATE_CONNECTOR_ID, key.connector_id)))
        permission = await session.find_one(CONNECTOR_PERMISSION_TABLE, query_all(AllOf((Equals(CONNECTOR_PERMISSION_CONNECTOR_ID, key.connector_id), OneOf(CONNECTOR_PERMISSION_GROUP_ID, groups))))) if groups else None
        if publication is None or not publication.published or permission is None:
            raise PersonalRefreshChanged()
        if await matching_rejection(session, self._cipher, connection):
            raise PersonalRefreshReconnectRequired()
        fingerprint = hashlib.sha256(json.dumps(definition.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return PersonalRefreshClaim(key=key, claim_id=claim_id, group_ids=groups, expected_revision=connection.revision, credential_fingerprint=authorization_fingerprint(connection.authorization), definition_fingerprint=fingerprint, policy=configuration.policy, grant=grant, deadline=deadline, status="preparing")

    async def reserve(self, command: ReservePersonalRefresh) -> PersonalRefreshClaim:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            now = max(command.now, self._clock())
            claim = await self._capture(session, command.key, command.group_ids, now, command.claim_id, now + timedelta(seconds=30))
            existing = await load_refresh(session, self._cipher, command.key)
            if existing is not None and existing.credential_fingerprint == claim.credential_fingerprint:
                if existing.status != "preparing" or existing.deadline > now:
                    if existing.status in ("refresh_uncertain", "refresh_denied") or existing.deadline <= now:
                        raise PersonalRefreshReconnectRequired()
                    raise PersonalRefreshConflict()
            from .personal_oauth_attempts import EncryptedPersonalOAuthAttemptStore, TerminalAttempt

            attempts = EncryptedPersonalOAuthAttemptStore(self._database, self._cipher, self._clock)
            rows = await session.find_many(PERSONAL_OAUTH_ATTEMPT_TABLE, query_all(AllOf((Equals(PERSONAL_OAUTH_ATTEMPT_NAMESPACE, command.key.principal.namespace), Equals(PERSONAL_OAUTH_ATTEMPT_SUBJECT, command.key.principal.subject), Equals(PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID, command.key.connector_id)))))
            for row in rows:
                attempt = attempts._decode(row)
                if not isinstance(attempt, TerminalAttempt) and attempt.expires_at > now:
                    raise PersonalRefreshConflict()
            await save_refresh(session, self._cipher, claim)
            return claim

    async def _owned(self, session: DatabaseSession, command: PersonalRefreshCommand) -> PersonalRefreshClaim:
        claim = await load_refresh(session, self._cipher, command.key)
        if claim is None or claim.claim_id != command.claim_id:
            raise PersonalRefreshChanged()
        return claim

    async def _revalidate(self, session: DatabaseSession, claim: PersonalRefreshClaim, now: datetime) -> None:
        if now >= claim.deadline:
            raise PersonalRefreshChanged()
        current = await self._capture(session, claim.key, claim.group_ids, now, claim.claim_id, claim.deadline)
        if current != claim.model_copy(update={"status": "preparing"}):
            raise PersonalRefreshChanged()

    async def exchange(self, command: PersonalRefreshCommand) -> PersonalRefreshClaim:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            claim = await self._owned(session, command)
            if claim.status != "preparing":
                raise PersonalRefreshConflict()
            await self._revalidate(session, claim, max(command.now, self._clock()))
            claim = claim.model_copy(update={"status": "exchanging"})
            await save_refresh(session, self._cipher, claim)
            return claim

    async def release(self, command: PersonalRefreshCommand) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            claim = await load_refresh(session, self._cipher, command.key)
            if claim is not None and claim.claim_id == command.claim_id and claim.status == "preparing":
                await clear_refresh(session, command.key)

    async def fail(self, command: FailPersonalRefresh) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            claim = await load_refresh(session, self._cipher, command.key)
            if claim is None or claim.claim_id != command.claim_id or claim.status != "exchanging":
                return
            connection = await load_personal_connection(session, self._cipher, command.key)
            if isinstance(connection, PersonalConnection) and isinstance(connection.authorization, Authorized) and authorization_fingerprint(connection.authorization) == claim.credential_fingerprint:
                await save_refresh(session, self._cipher, claim.model_copy(update={"status": command.reason}))

    async def complete(self, command: CompletePersonalRefresh) -> None:
        changed = False
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            claim = await self._owned(session, command)
            if claim.status != "exchanging":
                raise PersonalRefreshChanged()
            try:
                now = max(command.now, self._clock())
                await self._revalidate(session, claim, now)
                grant = PersonalOAuthGrant.model_validate_json(command.authorization.authorization.get_secret_value())
                old_binding = claim.grant.model_dump(exclude={"access_token", "refresh_token", "issued_at", "lifetime", "granted_scopes"})
                new_binding = grant.model_dump(exclude={"access_token", "refresh_token", "issued_at", "lifetime", "granted_scopes"})
                if old_binding != new_binding or not set(grant.granted_scopes).issubset(claim.grant.granted_scopes) or not isinstance(grant.lifetime, ExpiringPersonalToken) or grant.lifetime.expires_at <= now or grant.issued_at > now or not isinstance(grant.refresh_token, PresentPersonalRefreshToken):
                    raise PersonalRefreshChanged()
            except Exception:
                connection = await load_personal_connection(session, self._cipher, command.key)
                if isinstance(connection, PersonalConnection) and isinstance(connection.authorization, Authorized) and authorization_fingerprint(connection.authorization) == claim.credential_fingerprint:
                    await save_refresh(session, self._cipher, claim.model_copy(update={"status": "refresh_uncertain"}))
                changed = True
            else:
                connection = await load_personal_connection(session, self._cipher, command.key)
                replacement = connection.model_copy(update={"authorization": command.authorization, "revision": uuid4().hex})
                payload = replacement.model_dump(mode="json")
                payload["authorization"]["authorization"] = command.authorization.authorization.get_secret_value()
                key = PersonalConnectionRecordKey(namespace=claim.key.principal.namespace, subject=claim.key.principal.subject, connector_id=claim.key.connector_id)
                await session.upsert(PERSONAL_CONNECTION_TABLE, UpsertCommand(key=key, row=PersonalConnectionRecord(**key.model_dump(), document=self._cipher.encrypt(json.dumps(payload)))))
                await clear_refresh(session, command.key)
                await clear_rejection(session, command.key)
        if changed:
            raise PersonalRefreshChanged()
