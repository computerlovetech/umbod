import secrets
from datetime import datetime, timezone
from typing import Unpack

from pydantic import SecretStr

from umbod.core.persistence import Database

from .models import GeneratedPersonalAccessToken, PersonalAccessTokenPolicy
from .ports import PersonalAccessTokenOwnerOptions
from .service import PersonalAccessTokenService
from .store import DatabasePersonalAccessTokenStore


class UtcPersonalAccessTokenClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecurePersonalAccessTokenGenerator:
    def generate(self) -> GeneratedPersonalAccessToken:
        token_id = secrets.token_hex(16)
        secret = secrets.token_urlsafe(32)
        return GeneratedPersonalAccessToken(
            token_id=token_id,
            token=SecretStr(f"umbod_pat_v1_{token_id}_{secret}"),
        )


def create_personal_access_token_service(
    database: Database,
    policy: PersonalAccessTokenPolicy,
    **options: Unpack[PersonalAccessTokenOwnerOptions],
) -> PersonalAccessTokenService:
    return PersonalAccessTokenService(
        store=DatabasePersonalAccessTokenStore(database),
        clock=UtcPersonalAccessTokenClock(),
        generator=SecurePersonalAccessTokenGenerator(),
        policy=policy,
        **options,
    )
