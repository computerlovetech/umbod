from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from tests.persistence_runtime import prepared_inmemory_runtime

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.personal_access_tokens import (
    IssuePersonalAccessToken,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenService,
)
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore


class MutableClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2030, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def caller() -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://issuer"), subject="alice"
        ),
    )


@pytest.fixture
def request_token(clock: MutableClock) -> IssuePersonalAccessToken:
    return IssuePersonalAccessToken(
        name="automation",
        audience="telemetry",
        scopes=("telemetry:read",),
        expires_at=clock.now() + timedelta(days=1),
    )


@pytest_asyncio.fixture
async def store() -> AsyncIterator[DatabasePersonalAccessTokenStore]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield DatabasePersonalAccessTokenStore(runtime.database)
    finally:
        await runtime.shutdown()


@pytest.fixture
def service(
    clock: MutableClock,
    store: DatabasePersonalAccessTokenStore,
) -> PersonalAccessTokenService:
    return PersonalAccessTokenService(
        store=store,
        clock=clock,
        generator=SecurePersonalAccessTokenGenerator(),
        policy=PersonalAccessTokenPolicy(
            allowed_scopes=("telemetry:read", "telemetry:write")
        ),
    )
