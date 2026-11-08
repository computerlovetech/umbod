import hashlib

import pytest
from pydantic import SecretStr

from umbod.core.callers import CallerContext
from umbod.core.personal_access_tokens import (
    InvalidPersonalAccessToken,
    IssuePersonalAccessToken,
    PersonalAccessTokenCollision,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenService,
    ValidatePersonalAccessToken,
)
from umbod.core.personal_access_tokens.models import GeneratedPersonalAccessToken
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore

from .conftest import MutableClock

pytestmark = pytest.mark.asyncio


class CollidingGenerator:
    def __init__(self) -> None:
        self._counter = 0

    def generate(self) -> GeneratedPersonalAccessToken:
        self._counter += 1
        secret = "a" * 43 if self._counter == 1 else "b" * 43
        return GeneratedPersonalAccessToken(
            token_id="0" * 32,
            token=SecretStr("umbod_pat_v1_" + "0" * 32 + "_" + secret),
        )


async def test_collision_preserves_original_credentials_and_metadata(
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    clock: MutableClock,
    store: DatabasePersonalAccessTokenStore,
) -> None:
    service = PersonalAccessTokenService(
        store=store,
        clock=clock,
        generator=CollidingGenerator(),
        policy=PersonalAccessTokenPolicy(allowed_scopes=("telemetry:read",)),
    )
    issued = await service.issue(caller, request_token)
    with pytest.raises(PersonalAccessTokenCollision):
        await service.issue(caller, request_token)
    assert await service.list_tokens(caller) == (issued.metadata,)
    assert (
        await service.validate(
            ValidatePersonalAccessToken(
                token=issued.token,
                audience="telemetry",
                required_scopes=("telemetry:read",),
            )
        )
        == issued.metadata
    )
    replacement = SecretStr("umbod_pat_v1_" + "0" * 32 + "_" + "b" * 43)
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(
            ValidatePersonalAccessToken(
                token=replacement,
                audience="telemetry",
                required_scopes=("telemetry:read",),
            )
        )
    stored = await store.find(issued.metadata.token_id)
    assert stored is not None
    assert (
        stored.digest
        == hashlib.sha256(issued.token.get_secret_value().encode("ascii")).hexdigest()
    )
    assert stored.digest not in repr(stored)
    assert stored.digest not in stored.model_dump_json()
    assert issued.token.get_secret_value() not in stored.model_dump_json()
