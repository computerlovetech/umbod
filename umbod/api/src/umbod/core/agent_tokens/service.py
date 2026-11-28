import re
from base64 import urlsafe_b64encode
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest

from pydantic import SecretStr

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.administrator.operations import AdministratorAccess
from umbod.core.groups import GroupInstance, GroupInstanceId, GroupInstanceLookup

from .errors import (
    AgentCredentialConflict,
    AgentGroupNotFound,
    AgentNotFound,
    InvalidAgentCredential,
)
from .models import (
    AgentCredentialMetadata,
    AgentCredentialStatus,
    CreateAgent,
    IssuedAgentCredential,
    PublicMcpAgentIdentity,
    RotateAgentCredential,
    StoredAgentCredential,
)
from .ports import (
    AgentCredentialClock,
    AgentCredentialGenerator,
    AgentCredentialStore,
)

_AGENT_SECRET_BYTES = 32
_BEARER_PREFIX = "umbod_agent_v1_"
_BEARER_LENGTH = len(_BEARER_PREFIX) + 32 + 1 + 43
_AGENT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_BEARER_PATTERN = re.compile(
    rf"{_BEARER_PREFIX}({_AGENT_ID_PATTERN.pattern})_[A-Za-z0-9_-]{{43}}"
)


def _digest(bearer: str) -> str:
    return sha256(bearer.encode("ascii")).hexdigest()


class AgentCredentialService:
    def __init__(
        self,
        access: AdministratorAccess,
        groups: GroupInstanceLookup,
        store: AgentCredentialStore,
        clock: AgentCredentialClock,
        generator: AgentCredentialGenerator,
    ) -> None:
        self._access = access
        self._groups = groups
        self._store = store
        self._clock = clock
        self._generator = generator

    async def create(
        self, principal: AdministratorPrincipal, request: CreateAgent
    ) -> IssuedAgentCredential:
        self._access.require(principal)
        group = await self._require_group_instance(request.group_id)
        self._require_future_expiry(request.expires_at)
        agent_id = self._generator.generate_id().hex
        metadata = self._active_metadata(
            agent_id, request.display_name, group.group_id, request.expires_at
        )
        record, token = self._build_credential(metadata, group.instance_id)
        if not await self._store.insert(record):
            raise AgentCredentialConflict("Agent ID already exists")
        return IssuedAgentCredential(metadata=metadata, token=token)

    async def list_agents(
        self, principal: AdministratorPrincipal
    ) -> tuple[AgentCredentialMetadata, ...]:
        self._access.require(principal)
        credentials = await self._store.list_agents()
        now = self._now()
        return tuple(
            metadata.model_copy(update={"status": AgentCredentialStatus.EXPIRED})
            if metadata.status is AgentCredentialStatus.ACTIVE
            and metadata.expires_at <= now
            else metadata
            for metadata in credentials
        )

    async def rotate(
        self, principal: AdministratorPrincipal, request: RotateAgentCredential
    ) -> IssuedAgentCredential:
        self._access.require(principal)
        previous = await self._store.find(request.agent_id)
        if previous is None:
            raise AgentNotFound("Agent does not exist")
        current = previous.metadata
        group = await self._require_group_instance(current.group_id)
        if group.instance_id != previous.group_instance_id:
            raise AgentGroupNotFound("Agent group instance no longer exists")
        self._require_future_expiry(request.expires_at)
        metadata = self._active_metadata(
            current.agent_id, current.display_name, current.group_id, request.expires_at
        )
        replacement, token = self._build_credential(
            metadata, previous.group_instance_id
        )
        if metadata.credential_id == current.credential_id or compare_digest(
            previous.digest, replacement.digest
        ):
            raise AgentCredentialConflict("Credential must differ from its predecessor")

        def replacement_if_unexpired() -> StoredAgentCredential:
            self._require_future_expiry(request.expires_at)
            return replacement

        await self._replace(previous, replacement_if_unexpired)
        return IssuedAgentCredential(metadata=metadata, token=token)

    async def revoke(self, principal: AdministratorPrincipal, agent_id: str) -> bool:
        self._access.require(principal)
        if _AGENT_ID_PATTERN.fullmatch(agent_id) is None:
            return False
        previous = await self._store.find(agent_id)
        if (
            previous is None
            or previous.metadata.status is AgentCredentialStatus.REVOKED
        ):
            return False

        def revoked_credential() -> StoredAgentCredential:
            metadata = previous.metadata.model_copy(
                update={"status": AgentCredentialStatus.REVOKED}
            )
            return StoredAgentCredential(
                metadata=metadata,
                group_instance_id=previous.group_instance_id,
                digest=previous.digest,
            )

        await self._replace(previous, revoked_credential)
        return True

    async def verify_for_public_mcp(self, token: SecretStr) -> PublicMcpAgentIdentity:
        bearer = token.get_secret_value()
        if len(bearer) != _BEARER_LENGTH:
            raise InvalidAgentCredential()
        match = _BEARER_PATTERN.fullmatch(bearer)
        if match is None:
            raise InvalidAgentCredential()
        record = await self._store.find(match.group(1))
        if record is None or not compare_digest(record.digest, _digest(bearer)):
            raise InvalidAgentCredential()
        metadata = record.metadata
        if metadata.status is not AgentCredentialStatus.ACTIVE:
            raise InvalidAgentCredential()
        try:
            group = await self._require_group_instance(metadata.group_id)
        except Exception:
            raise InvalidAgentCredential() from None
        if (
            group.instance_id != record.group_instance_id
            or metadata.expires_at <= self._now()
        ):
            raise InvalidAgentCredential()
        return PublicMcpAgentIdentity(
            agent_id=metadata.agent_id,
            group_id=metadata.group_id,
            group_instance_id=group.instance_id,
            audience="umbod:mcp",
        )

    def _active_metadata(
        self, agent_id: str, display_name: str, group_id: str, expires_at: datetime
    ) -> AgentCredentialMetadata:
        credential_id = self._generator.generate_id().hex
        if agent_id == credential_id:
            raise AgentCredentialConflict("Agent and credential IDs must differ")
        return AgentCredentialMetadata(
            agent_id=agent_id,
            display_name=display_name,
            group_id=group_id,
            credential_id=credential_id,
            expires_at=expires_at,
            status=AgentCredentialStatus.ACTIVE,
        )

    def _build_credential(
        self, metadata: AgentCredentialMetadata, group_instance_id: GroupInstanceId
    ) -> tuple[StoredAgentCredential, SecretStr]:
        secret = self._generator.generate_secret(_AGENT_SECRET_BYTES)
        if len(secret) != _AGENT_SECRET_BYTES:
            raise ValueError("Agent credential generator returned an invalid secret")
        encoded = urlsafe_b64encode(secret).decode("ascii").rstrip("=")
        bearer = f"{_BEARER_PREFIX}{metadata.agent_id}_{encoded}"
        return StoredAgentCredential(
            metadata=metadata,
            group_instance_id=group_instance_id,
            digest=_digest(bearer),
        ), SecretStr(bearer)

    async def _require_group_instance(self, group_id: str) -> GroupInstance:
        group = await self._groups.find_group_instance(group_id)
        if group is None or group.group_id != group_id:
            raise AgentGroupNotFound("Agent group does not exist")
        return group

    def _require_future_expiry(self, expires_at: datetime) -> None:
        if expires_at <= self._now():
            raise ValueError("Expiry must be in the future")

    def _now(self) -> datetime:
        now = self._clock.now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Clock must return an aware datetime")
        return now

    async def _replace(
        self,
        previous: StoredAgentCredential,
        build_replacement: Callable[[], StoredAgentCredential],
    ) -> None:
        if not await self._store.compare_and_replace(previous, build_replacement):
            raise AgentCredentialConflict("Agent credential changed concurrently")
