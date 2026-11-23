import hashlib
import re
from datetime import timedelta
from functools import partial
from secrets import token_urlsafe

from pydantic import SecretStr

from umbod.core.harness_plugins import Harness

from .access import TELEMETRY_INGEST_SCOPE, TELEMETRY_TOKEN_AUDIENCE
from .install_claim_ports import InstallClaim, InstallClaimKey, InstallClaimStore, InvalidInstallClaim
from .models import IssuePersonalAccessToken, IssuedPersonalAccessToken, StoredPersonalAccessToken, TokenOwner
from .ports import PersonalAccessTokenClock
from .service import PersonalAccessTokenIssuer, checked_now

_CLAIM_CODE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_CLAIM_LIFETIME = timedelta(minutes=10)
_TOKEN_LIFETIME = timedelta(days=30)


def _claim_digest(code: str) -> str:
    if not _CLAIM_CODE.fullmatch(code):
        raise InvalidInstallClaim()
    return hashlib.sha256(code.encode("ascii")).hexdigest()


class InstallClaimService:
    def __init__(
        self, store: InstallClaimStore, clock: PersonalAccessTokenClock, issuer: PersonalAccessTokenIssuer,
    ) -> None:
        self._store = store
        self._clock = clock
        self._issuer = issuer

    async def create(self, owner: TokenOwner, harness: Harness, logs_endpoint: str) -> SecretStr:
        now = checked_now(self._clock)
        code = token_urlsafe(32)
        claim = InstallClaim(
            digest=_claim_digest(code), owner=owner, harness=harness,
            logs_endpoint=logs_endpoint, expires_at=now + _CLAIM_LIFETIME,
        )
        await self._store.create(claim, now)
        return SecretStr(code)

    async def redeem(self, harness: Harness, code: SecretStr, logs_endpoint: str) -> IssuedPersonalAccessToken:
        key = InstallClaimKey(digest=_claim_digest(code.get_secret_value()))
        return await self._store.redeem(key, harness, partial(self._build_token, logs_endpoint=logs_endpoint))

    def _build_token(
        self, claim: InstallClaim, *, logs_endpoint: str,
    ) -> tuple[StoredPersonalAccessToken, IssuedPersonalAccessToken]:
        now = checked_now(self._clock)
        if claim.logs_endpoint != logs_endpoint or claim.expires_at <= now:
            raise InvalidInstallClaim()
        return self._issuer.build(
            claim.owner,
            IssuePersonalAccessToken(
                name=f"{claim.harness} telemetry installer",
                audience=TELEMETRY_TOKEN_AUDIENCE,
                scopes=(TELEMETRY_INGEST_SCOPE,),
                expires_at=now + _TOKEN_LIFETIME,
            ),
            now,
        )
