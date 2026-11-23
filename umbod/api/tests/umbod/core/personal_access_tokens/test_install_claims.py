from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from tests.persistence_runtime import prepared_inmemory_runtime

from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered
from umbod.core.personal_access_tokens.access import TELEMETRY_INGEST_SCOPE, TELEMETRY_TOKEN_AUDIENCE, personal_access_token_policy
from umbod.core.personal_access_tokens.errors import PersonalAccessTokenCollision
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator
from umbod.core.personal_access_tokens.install_claim_ports import InvalidInstallClaim
from umbod.core.personal_access_tokens.install_claim_schema import CLAIM_TABLE
from umbod.core.personal_access_tokens.install_claim_store import DatabaseInstallClaimStore
from umbod.core.personal_access_tokens.install_claims import InstallClaimService
from umbod.core.personal_access_tokens.models import GeneratedPersonalAccessToken, IssuePersonalAccessToken, TokenOwner
from umbod.core.personal_access_tokens.service import PersonalAccessTokenIssuer
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore

from .conftest import MutableClock

_OWNER = TokenOwner(issuer="https://identity.example.test", subject="claim-owner")
_ENDPOINT = "https://collector.example.test/v1/logs"


@pytest_asyncio.fixture
async def claim_database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.fixture
def claim_service(claim_database: Database, clock: MutableClock) -> InstallClaimService:
    return InstallClaimService(
        DatabaseInstallClaimStore(claim_database), clock,
        PersonalAccessTokenIssuer(SecurePersonalAccessTokenGenerator(), personal_access_token_policy()),
    )


@pytest.mark.asyncio
async def test_claim_cannot_be_redeemed_at_expires_at(
    claim_service: InstallClaimService, claim_database: Database, clock: MutableClock,
) -> None:
    code = await claim_service.create(_OWNER, "codex", _ENDPOINT)
    clock.instant += timedelta(minutes=10)
    with pytest.raises(InvalidInstallClaim):
        await claim_service.redeem("codex", code, _ENDPOINT)
    assert await DatabasePersonalAccessTokenStore(claim_database).list_tokens(_OWNER) == ()


@pytest.mark.asyncio
async def test_new_claim_prunes_expired_claims_only(
    claim_service: InstallClaimService, claim_database: Database, clock: MutableClock,
) -> None:
    await claim_service.create(_OWNER, "codex", _ENDPOINT)
    clock.instant += timedelta(minutes=9)
    await claim_service.create(_OWNER, "claude-code", _ENDPOINT)
    clock.instant += timedelta(minutes=1)
    await claim_service.create(_OWNER, "claude-code", _ENDPOINT)
    async with claim_database.read_session() as session:
        rows = await session.find_many(CLAIM_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert [claim.harness for claim in rows] == ["claude-code", "claude-code"]


class FixedTokenGenerator:
    def __init__(self) -> None:
        self.token = SecurePersonalAccessTokenGenerator().generate()

    def generate(self) -> GeneratedPersonalAccessToken:
        return self.token


@pytest.mark.asyncio
async def test_token_insert_collision_rolls_back_claim_deletion(
    claim_service: InstallClaimService, claim_database: Database, clock: MutableClock,
) -> None:
    issuer = PersonalAccessTokenIssuer(FixedTokenGenerator(), personal_access_token_policy())
    token_store = DatabasePersonalAccessTokenStore(claim_database)
    existing, _ = issuer.build(
        _OWNER,
        IssuePersonalAccessToken(
            name="existing", audience=TELEMETRY_TOKEN_AUDIENCE, scopes=(TELEMETRY_INGEST_SCOPE,),
            expires_at=clock.now() + timedelta(days=1),
        ),
        clock.now(),
    )
    assert await token_store.insert(existing)
    collision_service = InstallClaimService(DatabaseInstallClaimStore(claim_database), clock, issuer)
    code = await claim_service.create(_OWNER, "codex", _ENDPOINT)
    with pytest.raises(PersonalAccessTokenCollision):
        await collision_service.redeem("codex", code, _ENDPOINT)
    issued = await claim_service.redeem("codex", code, _ENDPOINT)
    assert issued.metadata.expires_at == clock.now() + timedelta(days=30)
    assert set(await token_store.list_tokens(_OWNER)) == {existing.metadata, issued.metadata}
