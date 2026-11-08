import asyncio
import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.personal_access_tokens import (
    InvalidPersonalAccessToken,
    IssuePersonalAccessToken,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenStatus,
    ValidatePersonalAccessToken,
    create_personal_access_token_service,
)

from umbod.core.personal_access_tokens.models import StoredPersonalAccessToken
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore


def _caller(subject: str) -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://identity.example.test"),
            subject=subject,
        ),
    )


def _policy() -> PersonalAccessTokenPolicy:
    return PersonalAccessTokenPolicy(allowed_scopes=("telemetry:write",))


def _request() -> IssuePersonalAccessToken:
    return IssuePersonalAccessToken(
        name="Codex on Mac",
        audience="umbod-telemetry",
        scopes=("telemetry:write",),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_token_survives_runtime_restart_with_only_its_hash_persisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-access-tokens.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        issued = await service.issue(_caller("alice"), _request())
    finally:
        await runtime.shutdown()

    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        validated = await service.validate(
            ValidatePersonalAccessToken(
                token=issued.token,
                audience="umbod-telemetry",
                required_scopes=("telemetry:write",),
            )
        )
        assert validated == issued.metadata
        assert await service.list_tokens(_caller("alice")) == (issued.metadata,)
        assert await service.list_tokens(_caller("bob")) == ()
    finally:
        await runtime.shutdown()

    bearer = issued.token.get_secret_value()
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT * FROM personal_access_tokens").fetchall()
    stored = repr(rows)
    assert bearer not in stored
    assert bearer[-43:] not in stored
    assert hashlib.sha256(bearer.encode("ascii")).hexdigest() in stored
    assert bearer.encode("ascii") not in path.read_bytes()


@pytest.mark.asyncio
async def test_revocation_is_visible_to_another_runtime_without_cached_authorization(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared-personal-access-tokens.sqlite3"
    first = await prepared_sqlite_runtime(path)
    try:
        second = await prepared_sqlite_runtime(path)
        try:
            issuer = create_personal_access_token_service(first.database, _policy())
            receiver = create_personal_access_token_service(second.database, _policy())
            issued = await issuer.issue(_caller("alice"), _request())
            validation = ValidatePersonalAccessToken(
                token=issued.token,
                audience="umbod-telemetry",
                required_scopes=("telemetry:write",),
            )
            assert await receiver.validate(validation) == issued.metadata
            assert await issuer.revoke(_caller("alice"), issued.metadata.token_id)
            with pytest.raises(InvalidPersonalAccessToken):
                await receiver.validate(validation)
            assert await receiver.list_tokens(_caller("alice")) == ()
            assert await DatabasePersonalAccessTokenStore(second.database).find(
                issued.metadata.token_id
            ) is None
        finally:
            await second.shutdown()
    finally:
        await first.shutdown()


@pytest.mark.asyncio
async def test_token_schema_initialization_preserves_existing_database_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing-database.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute("CREATE TABLE existing_content (value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO existing_content VALUES (?)", ("preserved",)
            )
    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        await service.issue(_caller("alice"), _request())
        await runtime.readiness.ensure_ready()
    finally:
        await runtime.shutdown()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT value FROM existing_content").fetchall() == [
            ("preserved",)
        ]
        assert connection.execute(
            "SELECT count(*) FROM personal_access_tokens"
        ).fetchone() == (1,)


@pytest.mark.asyncio
async def test_legacy_revoked_token_deletion_is_durable(tmp_path: Path) -> None:
    path = tmp_path / "legacy-personal-access-tokens.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        issued = await service.issue(_caller("alice"), _request())
        metadata = issued.metadata.model_copy(
            update={"token_id": "f" * 32, "status": PersonalAccessTokenStatus.REVOKED}
        )
        store = DatabasePersonalAccessTokenStore(runtime.database)
        assert await store.insert(
            StoredPersonalAccessToken(metadata=metadata, digest="0" * 64)
        )
    finally:
        await runtime.shutdown()

    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        assert metadata in await service.list_tokens(_caller("alice"))
        assert not await service.revoke(_caller("bob"), metadata.token_id)
        assert await service.revoke(_caller("alice"), metadata.token_id)
    finally:
        await runtime.shutdown()

    runtime = await prepared_sqlite_runtime(path)
    try:
        service = create_personal_access_token_service(runtime.database, _policy())
        assert await service.list_tokens(_caller("alice")) == (issued.metadata,)
        assert not await service.revoke(_caller("alice"), metadata.token_id)
    finally:
        await runtime.shutdown()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT token_id FROM personal_access_tokens"
        ).fetchall() == [(issued.metadata.token_id,)]


@pytest.mark.asyncio
async def test_concurrent_owner_revocations_delete_token_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "concurrent-personal-access-tokens.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        first = create_personal_access_token_service(runtime.database, _policy())
        second = create_personal_access_token_service(runtime.database, _policy())
        issued = await first.issue(_caller("alice"), _request())
        results = await asyncio.gather(
            first.revoke(_caller("alice"), issued.metadata.token_id),
            second.revoke(_caller("alice"), issued.metadata.token_id),
        )
        assert sorted(results) == [False, True]
        assert await first.list_tokens(_caller("alice")) == ()
        assert await DatabasePersonalAccessTokenStore(runtime.database).find(
            issued.metadata.token_id
        ) is None
    finally:
        await runtime.shutdown()
