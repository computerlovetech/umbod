import hashlib
import hmac
import re
from datetime import datetime
from typing import Unpack

from umbod.core.callers import CallerContext

from .errors import (
    InvalidPersonalAccessToken,
    PersonalAccessTokenCollision,
)
from .models import (
    IssuePersonalAccessToken,
    IssuedPersonalAccessToken,
    PersonalAccessTokenMetadata,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenStatus,
    StoredPersonalAccessToken,
    ValidatePersonalAccessToken,
)
from .ownership import VerifiedPersonalAccessTokenOwnerResolver
from .ports import (
    PersonalAccessTokenOwnerOptions,
    PersonalAccessTokenClock,
    PersonalAccessTokenGenerator,
    PersonalAccessTokenStore,
)

TOKEN_PREFIX = "umbod_pat_v1_"
TOKEN_LENGTH = len(TOKEN_PREFIX) + 32 + 1 + 43
TOKEN_PATTERN = re.compile(r"umbod_pat_v1_([0-9a-f]{32})_([A-Za-z0-9_-]{43})", re.ASCII)


def checked_now(clock: PersonalAccessTokenClock) -> datetime:
    now = clock.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Clock must return an aware datetime")
    return now


class PersonalAccessTokenService:
    def __init__(
        self,
        store: PersonalAccessTokenStore,
        clock: PersonalAccessTokenClock,
        generator: PersonalAccessTokenGenerator,
        policy: PersonalAccessTokenPolicy,
        **options: Unpack[PersonalAccessTokenOwnerOptions],
    ) -> None:
        self._store = store
        self._clock = clock
        self._generator = generator
        self._policy = policy
        self._owner_resolver = options.get(
            "owner_resolver", VerifiedPersonalAccessTokenOwnerResolver()
        )

    async def issue(
        self,
        caller: CallerContext,
        request: IssuePersonalAccessToken,
    ) -> IssuedPersonalAccessToken:
        owner = self._owner_resolver.resolve(caller)
        now = checked_now(self._clock)
        if request.expires_at <= now:
            raise ValueError("Expiry must be in the future")
        if not set(request.scopes).issubset(self._policy.allowed_scopes):
            raise ValueError("Unsupported personal access token scopes")
        generated = self._generator.generate()
        bearer = generated.token.get_secret_value()
        match = TOKEN_PATTERN.fullmatch(bearer)
        if match is None or match.group(1) != generated.token_id:
            raise ValueError("Token generator returned an invalid token")
        metadata = PersonalAccessTokenMetadata(
            token_id=generated.token_id,
            owner=owner,
            name=request.name,
            audience=request.audience,
            scopes=request.scopes,
            created_at=now,
            expires_at=request.expires_at,
            status=PersonalAccessTokenStatus.ACTIVE,
        )
        stored = StoredPersonalAccessToken(
            metadata=metadata,
            digest=hashlib.sha256(bearer.encode("ascii")).hexdigest(),
        )
        if not await self._store.insert(stored):
            raise PersonalAccessTokenCollision()
        return IssuedPersonalAccessToken(token=generated.token, metadata=metadata)

    async def list_tokens(
        self, caller: CallerContext
    ) -> tuple[PersonalAccessTokenMetadata, ...]:
        return await self._store.list_tokens(self._owner_resolver.resolve(caller))

    async def revoke(self, caller: CallerContext, token_id: str) -> bool:
        owner = self._owner_resolver.resolve(caller)
        if re.fullmatch(r"[0-9a-f]{32}", token_id, re.ASCII) is None:
            return False
        return await self._store.revoke(owner, token_id)

    async def validate(
        self, request: ValidatePersonalAccessToken
    ) -> PersonalAccessTokenMetadata:
        bearer = request.token.get_secret_value()
        if len(bearer) != TOKEN_LENGTH:
            raise InvalidPersonalAccessToken()
        match = TOKEN_PATTERN.fullmatch(bearer)
        if match is None:
            raise InvalidPersonalAccessToken()
        record = await self._store.find(match.group(1))
        if record is None:
            raise InvalidPersonalAccessToken()
        digest = hashlib.sha256(bearer.encode("ascii")).hexdigest()
        if not hmac.compare_digest(record.digest, digest):
            raise InvalidPersonalAccessToken()
        metadata = record.metadata
        if (
            metadata.status != PersonalAccessTokenStatus.ACTIVE
            or checked_now(self._clock) >= metadata.expires_at
            or request.audience != metadata.audience
            or not set(request.required_scopes).issubset(metadata.scopes)
        ):
            raise InvalidPersonalAccessToken()
        return metadata
