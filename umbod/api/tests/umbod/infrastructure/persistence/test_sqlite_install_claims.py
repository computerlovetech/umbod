import asyncio
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import SecretStr
from tests.persistence_runtime import prepared_sqlite_runtime

from umbod.core.persistence import Database
from umbod.core.personal_access_tokens.access import personal_access_token_policy
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator, UtcPersonalAccessTokenClock
from umbod.core.personal_access_tokens.install_claim_ports import InvalidInstallClaim
from umbod.core.personal_access_tokens.install_claim_store import DatabaseInstallClaimStore
from umbod.core.personal_access_tokens.install_claims import InstallClaimService
from umbod.core.personal_access_tokens.models import IssuedPersonalAccessToken, TokenOwner
from umbod.core.personal_access_tokens.service import PersonalAccessTokenIssuer
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore

_OWNER = TokenOwner(issuer="https://identity.example.test", subject="claim-owner")
_ENDPOINT = "https://collector.example.test/v1/logs"


def service(database: Database) -> InstallClaimService:
    return InstallClaimService(
        DatabaseInstallClaimStore(database), UtcPersonalAccessTokenClock(),
        PersonalAccessTokenIssuer(SecurePersonalAccessTokenGenerator(), personal_access_token_policy()),
    )


async def redeem(claims: InstallClaimService, code: SecretStr) -> IssuedPersonalAccessToken | InvalidInstallClaim:
    try:
        return await claims.redeem("codex", code, _ENDPOINT)
    except InvalidInstallClaim as error:
        return error


@pytest.mark.asyncio
async def test_concurrent_claim_redemption_across_database_runtimes_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite3"
    first = await prepared_sqlite_runtime(path)
    try:
        second = await prepared_sqlite_runtime(path)
        try:
            issuer, competitor = service(first.database), service(second.database)
            code = await issuer.create(_OWNER, "codex", _ENDPOINT)
            results = await asyncio.gather(redeem(issuer, code), redeem(competitor, code))
            winners = [result for result in results if isinstance(result, IssuedPersonalAccessToken)]
            assert len(winners) == 1
            assert await DatabasePersonalAccessTokenStore(first.database).list_tokens(_OWNER) == (winners[0].metadata,)
        finally:
            await second.shutdown()
    finally:
        await first.shutdown()


@pytest.mark.asyncio
async def test_sqlite_persists_only_the_claim_digest(tmp_path: Path) -> None:
    path = tmp_path / "claims.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        secret = (await service(runtime.database).create(_OWNER, "codex", _ENDPOINT)).get_secret_value()
    finally:
        await runtime.shutdown()
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT * FROM telemetry_install_claims").fetchall()
    assert secret not in repr(rows)
    assert hashlib.sha256(secret.encode("ascii")).hexdigest() in repr(rows)
    assert secret.encode("ascii") not in path.read_bytes()
