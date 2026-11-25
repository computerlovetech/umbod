import json
from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from pydantic import Field, SecretStr, TypeAdapter

from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import Database, DatabaseSession, Equals, TransactionMode, UpsertCommand
from ..personal.oauth.applications import (
    ClaimedOAuthApplication,
    CompleteOAuthApplication,
    ExpiringApplicationSecret,
    OAuthApplicationBinding,
    OAuthApplicationUnavailable,
    ReadyOAuthApplication,
    ResolveOAuthApplication,
)
from .personal_oauth_application_schema import (
    PERSONAL_OAUTH_APPLICATION_TABLE, PERSONAL_OAUTH_APPLICATION_CONNECTOR_ID,
    PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID, PersonalOAuthApplicationKey, PersonalOAuthApplicationRecord,
)
from .personal_oauth_configurations import load_personal_oauth_configuration
from .queries import query_all
from .schema import CONNECTOR_DEFINITION_TABLE, CONNECTOR_DEFINITION_CONNECTOR_ID
from .ports import CONNECTOR_DEFINITION_ADAPTER
from ..personal.oauth.grants import PersonalOAuthGrant

_APPLICATION = TypeAdapter(Annotated[ClaimedOAuthApplication | ReadyOAuthApplication, Field(discriminator="kind")])


def _serialize(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Unsupported application value")


async def load_bound_oauth_application(session: DatabaseSession, cipher: TextCipher, query: ResolveOAuthApplication, now: datetime) -> ReadyOAuthApplication:
    row = await session.find_one(PERSONAL_OAUTH_APPLICATION_TABLE, query_all(Equals(PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID, query.reference.registration_id)))
    if row is None:
        raise OAuthApplicationUnavailable()
    ready = _APPLICATION.validate_json(cipher.decrypt(row.document))
    if (
        not isinstance(ready, ReadyOAuthApplication)
        or ready.registration_id != row.registration_id
        or ready.binding.connector_id != row.connector_id
        or ready.binding != query.binding
        or ready.credentials.client_id != query.client_id
        or (isinstance(ready.credentials.lifetime, ExpiringApplicationSecret) and ready.credentials.lifetime.expires_at <= now)
    ):
        raise OAuthApplicationUnavailable()
    return ready


async def require_grant_application(session: DatabaseSession, cipher: TextCipher, grant: PersonalOAuthGrant, now: datetime) -> None:
    if grant.client_mode != "dynamic_confidential":
        return
    if grant.application_reference.kind != "registered" or grant.token_endpoint_auth_method == "none":
        raise OAuthApplicationUnavailable()
    await load_bound_oauth_application(session, cipher, ResolveOAuthApplication(
        reference=grant.application_reference, client_id=grant.client_id,
        binding=OAuthApplicationBinding(
            connector_id=grant.key.connector_id, configuration_revision=grant.configuration_revision,
            issuer=grant.issuer, resource=grant.resource, redirect_uri=grant.redirect_uri,
            token_endpoint=grant.token_endpoint, requested_scopes=grant.requested_scopes,
            token_endpoint_auth_method=grant.token_endpoint_auth_method,
        ),
    ), now)


class UnavailablePersonalOAuthApplicationStore:
    async def reserve(self, binding: OAuthApplicationBinding) -> ClaimedOAuthApplication | ReadyOAuthApplication:
        raise OAuthApplicationUnavailable()

    async def complete(self, command: CompleteOAuthApplication) -> ReadyOAuthApplication:
        raise OAuthApplicationUnavailable()

    async def resolve(self, query: ResolveOAuthApplication) -> ReadyOAuthApplication:
        raise OAuthApplicationUnavailable()


class EncryptedPersonalOAuthApplicationStore:
    def __init__(self, database: Database, cipher: TextCipher, clock: Callable[[], datetime]) -> None:
        self._database = database
        self._cipher = cipher
        self._clock = clock

    def _decode(self, row: PersonalOAuthApplicationRecord) -> ClaimedOAuthApplication | ReadyOAuthApplication:
        application = _APPLICATION.validate_json(self._cipher.decrypt(row.document))
        if application.registration_id != row.registration_id or application.binding.connector_id != row.connector_id:
            raise OAuthApplicationUnavailable()
        return application

    async def _current(self, session: DatabaseSession, binding: OAuthApplicationBinding) -> None:
        definition = await session.find_one(CONNECTOR_DEFINITION_TABLE, query_all(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, binding.connector_id)))
        if definition is None or CONNECTOR_DEFINITION_ADAPTER.validate_python(definition.document).endpoint_url != binding.resource:
            raise OAuthApplicationUnavailable()
        configuration = await load_personal_oauth_configuration(session, self._cipher, binding.connector_id)
        client = configuration.policy.client
        if (
            client.kind != "dynamic_confidential"
            or configuration.policy.revision != binding.configuration_revision
            or configuration.policy.requested_scopes != binding.requested_scopes
            or client.token_endpoint_auth_method != binding.token_endpoint_auth_method
            or (client.approved_issuers and binding.issuer not in client.approved_issuers)
        ):
            raise OAuthApplicationUnavailable()

    def _valid(self, application: ReadyOAuthApplication) -> bool:
        lifetime = application.credentials.lifetime
        return not isinstance(lifetime, ExpiringApplicationSecret) or lifetime.expires_at > self._clock()

    async def _save(self, session: DatabaseSession, application: ClaimedOAuthApplication | ReadyOAuthApplication) -> None:
        await session.upsert(PERSONAL_OAUTH_APPLICATION_TABLE, UpsertCommand(
            key=PersonalOAuthApplicationKey(registration_id=application.registration_id),
            row=PersonalOAuthApplicationRecord(
                registration_id=application.registration_id, connector_id=application.binding.connector_id,
                document=self._cipher.encrypt(json.dumps(application.model_dump(mode="python"), default=_serialize)),
            ),
        ))

    async def reserve(self, binding: OAuthApplicationBinding) -> ClaimedOAuthApplication | ReadyOAuthApplication:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await self._current(session, binding)
            rows = await session.find_many(PERSONAL_OAUTH_APPLICATION_TABLE, query_all(Equals(PERSONAL_OAUTH_APPLICATION_CONNECTOR_ID, binding.connector_id)))
            matching: list[ReadyOAuthApplication] = []
            for row in rows:
                application = self._decode(row)
                if application.binding.configuration_revision != binding.configuration_revision:
                    continue
                if application.binding != binding:
                    continue
                if isinstance(application, ClaimedOAuthApplication):
                    raise OAuthApplicationUnavailable()
                if self._valid(application):
                    matching.append(application)
            if len(matching) > 1:
                raise OAuthApplicationUnavailable()
            if matching:
                return matching[0]
            claim = ClaimedOAuthApplication(registration_id=uuid4().hex, claim_id=uuid4().hex, binding=binding)
            await self._save(session, claim)
            return claim

    async def complete(self, command: CompleteOAuthApplication) -> ReadyOAuthApplication:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await self._current(session, command.claim.binding)
            row = await session.find_one(PERSONAL_OAUTH_APPLICATION_TABLE, query_all(Equals(PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID, command.claim.registration_id)))
            if row is None or self._decode(row) != command.claim:
                raise OAuthApplicationUnavailable()
            ready = ReadyOAuthApplication(registration_id=command.claim.registration_id, binding=command.claim.binding, credentials=command.credentials)
            if not self._valid(ready):
                raise OAuthApplicationUnavailable()
            await self._save(session, ready)
            return ready

    async def resolve(self, query: ResolveOAuthApplication) -> ReadyOAuthApplication:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            await self._current(session, query.binding)
            return await load_bound_oauth_application(session, self._cipher, query, self._clock())
