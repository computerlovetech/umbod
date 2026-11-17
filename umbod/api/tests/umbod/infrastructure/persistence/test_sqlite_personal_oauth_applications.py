import asyncio
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.personal_oauth_applications import application_clock, application_credentials, install_application_policy
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_oauth_applications.models import (
    ClaimedOAuthApplication, CompleteOAuthApplication, OAuthApplicationUnavailable,
    RegisteredApplicationReference, ResolveOAuthApplication,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_applications import EncryptedPersonalOAuthApplicationStore


@pytest.mark.asyncio
async def test_sqlite_application_credentials_are_encrypted_and_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "applications.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        binding = await install_application_policy(runtime.database)
        store = EncryptedPersonalOAuthApplicationStore(runtime.database, AuthenticatedTextCipher("test-secret"), application_clock)
        claim = await store.reserve(binding)
        assert isinstance(claim, ClaimedOAuthApplication)
        ready = await store.complete(CompleteOAuthApplication(claim=claim, credentials=application_credentials()))
    finally:
        await runtime.shutdown()
    assert b"private-registered-secret-sentinel" not in path.read_bytes()
    assert b"registered-client" not in path.read_bytes()
    reopened = await prepared_sqlite_runtime(path)
    try:
        store = EncryptedPersonalOAuthApplicationStore(reopened.database, AuthenticatedTextCipher("test-secret"), application_clock)
        assert await store.reserve(binding) == ready
        assert await store.resolve(ResolveOAuthApplication(
            reference=RegisteredApplicationReference(registration_id=ready.registration_id), binding=binding, client_id=ready.credentials.client_id,
        )) == ready
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_sqlite_cross_instance_concurrent_initial_registration_has_one_owner(tmp_path: Path) -> None:
    path = tmp_path / "applications.sqlite3"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    try:
        binding = await install_application_policy(first.database)
        stores = [EncryptedPersonalOAuthApplicationStore(runtime.database, AuthenticatedTextCipher("test-secret"), application_clock) for runtime in (first, second)]
        outcomes = await asyncio.gather(*(store.reserve(binding) for store in stores), return_exceptions=True)
        claims = [outcome for outcome in outcomes if isinstance(outcome, ClaimedOAuthApplication)]
        assert len(claims) == 1
        assert sum(isinstance(outcome, OAuthApplicationUnavailable) for outcome in outcomes) == 1
        ready = await stores[0].complete(CompleteOAuthApplication(claim=claims[0], credentials=application_credentials()))
        assert await stores[1].reserve(binding) == ready
    finally:
        await second.shutdown()
        await first.shutdown()


@pytest.mark.asyncio
async def test_sqlite_abandoned_claim_survives_restart_and_never_replays(tmp_path: Path) -> None:
    path = tmp_path / "applications.sqlite3"
    first = await prepared_sqlite_runtime(path)
    try:
        binding = await install_application_policy(first.database)
        await EncryptedPersonalOAuthApplicationStore(first.database, AuthenticatedTextCipher("test-secret"), application_clock).reserve(binding)
    finally:
        await first.shutdown()
    second = await prepared_sqlite_runtime(path)
    try:
        with pytest.raises(OAuthApplicationUnavailable):
            await EncryptedPersonalOAuthApplicationStore(second.database, AuthenticatedTextCipher("test-secret"), application_clock).reserve(binding)
    finally:
        await second.shutdown()
