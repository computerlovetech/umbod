import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
)

from ..personal_oauth_configuration import (
    PersonalOAuthConfigurationStore, PersonalOAuthConfigurationQuery,
    PersonalOAuthConfigurationUnavailable, parse_oauth_scopes,
)

from .inventory_models import PersonalConnectorQuery, PersonalConnectorUnavailable, VerifiedGroupMembership
from .inventory_ports import PersonalConnectorInventory
from .models import MissingCanonicalPrincipal, PersonalConnection, PersonalConnectionKey
from .oauth_models import (
    ClaimPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    ExchangePersonalOAuth,
    FailPersonalOAuthAttempt,
    PersonalOAuthAttemptQuery,
    PersonalOAuthAttemptView,
    PersonalOAuthConflict,
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PersonalOAuthStartResult,
    PersonalOAuthUnavailable,
    PreparePersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from .oauth_ports import PersonalOAuthAttemptStore, PersonalOAuthProvider
from .ports import CanonicalPrincipalProvider, PersonalConnectionStore


class PersonalOAuthService:
    def __init__(
        self,
        principals: CanonicalPrincipalProvider,
        groups: VerifiedGroupMembership,
        inventory: PersonalConnectorInventory,
        definitions: ConnectorDefinitionStore,
        connections: PersonalConnectionStore,
        attempts: PersonalOAuthAttemptStore,
        provider: PersonalOAuthProvider,
        redirect_uri: str,
        clock: Callable[[], datetime],
        configurations: PersonalOAuthConfigurationStore,
    ) -> None:
        self._principals = principals
        self._groups = groups
        self._inventory = inventory
        self._definitions = definitions
        self._connections = connections
        self._attempts = attempts
        self._provider = provider
        self._redirect_uri = redirect_uri
        self._clock = clock
        self._configurations = configurations

    async def _key(self, connector_id: str) -> PersonalConnectionKey:
        principal = await self._principals.get_principal()
        if principal is None:
            raise MissingCanonicalPrincipal()
        return PersonalConnectionKey(principal=principal, connector_id=connector_id)

    async def start(self, connector_id: str) -> PersonalOAuthStartResult:
        try:
            selection = await self._inventory.get(PersonalConnectorQuery(connector_id=connector_id))
        except PersonalConnectorUnavailable:
            raise PersonalOAuthUnavailable() from None
        if not selection.enabled:
            raise PersonalOAuthUnavailable()
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if (
            not isinstance(result, ConnectorDefinitionFound)
            or not isinstance(result.definition, OAuthConnectorDefinition)
            or result.definition.authorization_mode != "personal"
        ):
            raise PersonalOAuthUnavailable()
        key = await self._key(connector_id)
        connection = await self._connections.get(key)
        if not isinstance(connection, PersonalConnection) or not connection.enabled:
            raise PersonalOAuthUnavailable()
        try:
            configuration = await self._configurations.get(PersonalOAuthConfigurationQuery(connector_id=connector_id))
        except PersonalOAuthConfigurationUnavailable:
            raise PersonalOAuthUnavailable() from None
        attempt_id = uuid4().hex
        now = self._clock()
        preparation = PreparePersonalOAuth(
            endpoint_url=str(result.definition.endpoint_url),
            redirect_uri=self._redirect_uri,
            state=SecretStr(attempt_id + "." + secrets.token_urlsafe(32)),
            code_verifier=SecretStr(secrets.token_urlsafe(64)),
            policy=configuration.policy,
        )
        reservation = ReservePersonalOAuthAttempt(
            key=key,
            attempt_id=attempt_id,
            expected_revision=connection.revision,
            definition_fingerprint=hashlib.sha256(json.dumps(
                result.definition.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest(),
            endpoint_url=preparation.endpoint_url,
            group_ids=self._groups.group_ids,
            preparation=preparation,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        await self._attempts.reserve(reservation)
        try:
            prepared = await self._provider.prepare(reservation.preparation)
            attempt = await self._attempts.publish(PublishPersonalOAuthAttempt(
                query=PersonalOAuthAttemptQuery(key=key, attempt_id=attempt_id, now=self._clock()),
                prepared=prepared,
            ))
        except BaseException as error:
            await asyncio.shield(self._attempts.abort_preparation(PersonalOAuthAttemptQuery(
                key=key, attempt_id=attempt_id, now=self._clock(),
            )))
            if isinstance(error, (PersonalOAuthProviderUnsupported, PersonalOAuthProviderFailure,
                                  PersonalOAuthUnavailable, PersonalOAuthConflict, asyncio.CancelledError)):
                raise
            if not isinstance(error, Exception):
                raise
            raise PersonalOAuthProviderFailure() from None
        return PersonalOAuthStartResult(attempt=attempt, authorization_url=prepared.authorization_url)

    async def get(self, connector_id: str, attempt_id: str) -> PersonalOAuthAttemptView:
        return await self._attempts.get(PersonalOAuthAttemptQuery(
            key=await self._key(connector_id), attempt_id=attempt_id, now=self._clock(),
        ))

    async def cancel(self, connector_id: str, attempt_id: str) -> PersonalOAuthAttemptView:
        return await self._attempts.cancel(PersonalOAuthAttemptQuery(
            key=await self._key(connector_id), attempt_id=attempt_id, now=self._clock(),
        ))


class PersonalOAuthCallbackService:
    def __init__(
        self, attempts: PersonalOAuthAttemptStore, provider: PersonalOAuthProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._attempts = attempts
        self._provider = provider
        self._clock = clock

    async def finish(self, state: str, code: str, issuer: str, error: str, scope: str) -> None:
        attempt = await self._attempts.claim(ClaimPersonalOAuthAttempt(
            state=SecretStr(state), claim_id=uuid4().hex, now=self._clock(),
        ))
        try:
            if error or not set(parse_oauth_scopes(scope)).issubset(attempt.preparation.policy.requested_scopes):
                raise PersonalOAuthProviderFailure()
            authorization = await self._provider.exchange(ExchangePersonalOAuth(
                attempt=attempt, code=SecretStr(code), issuer=issuer,
            ))
            await self._attempts.complete(CompletePersonalOAuthAttempt(
                query=attempt.query.model_copy(update={"now": self._clock()}),
                claim_id=attempt.claim_id, authorization=authorization,
            ))
        except BaseException as failure:
            await asyncio.shield(self._attempts.fail(FailPersonalOAuthAttempt(
                query=attempt.query.model_copy(update={"now": self._clock()}),
                claim_id=attempt.claim_id,
            )))
            if not isinstance(failure, Exception):
                raise
            raise PersonalOAuthProviderFailure() from None
