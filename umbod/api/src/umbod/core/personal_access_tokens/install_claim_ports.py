from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Protocol

from pydantic import Field, StringConstraints

from umbod.core.credential_expiry import UtcDatetime
from umbod.core.harness_plugins import Harness

from .models import IssuedPersonalAccessToken, StoredPersonalAccessToken, TokenModel, TokenOwner

ClaimDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class InstallClaimKey(TokenModel):
    digest: ClaimDigest = Field(repr=False)


class InstallClaim(InstallClaimKey):
    owner: TokenOwner
    harness: Harness
    logs_endpoint: Annotated[str, StringConstraints(min_length=1)]
    expires_at: UtcDatetime


BuildInstallToken = Callable[[InstallClaim], tuple[StoredPersonalAccessToken, IssuedPersonalAccessToken]]


class InvalidInstallClaim(ValueError):
    pass


class InstallClaimStore(Protocol):
    async def create(self, claim: InstallClaim, now: datetime) -> None: ...

    async def redeem(
        self, key: InstallClaimKey, harness: Harness, build_token: BuildInstallToken,
    ) -> IssuedPersonalAccessToken: ...
