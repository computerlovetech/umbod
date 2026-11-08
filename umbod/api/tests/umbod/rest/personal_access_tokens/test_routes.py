from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.persistence import PersistenceRuntime
from umbod.core.personal_access_tokens import (
    InvalidPersonalAccessToken,
    IssuePersonalAccessToken,
    PersonalAccessTokenService,
    PersonalAccessTokenStatus,
    ValidatePersonalAccessToken,
)
from umbod.core.personal_access_tokens.factory import (
    create_personal_access_token_service,
)
from umbod.core.personal_access_tokens.access import (
    TELEMETRY_INGEST_SCOPE,
    TELEMETRY_TOKEN_AUDIENCE,
    personal_access_token_policy,
)
from umbod.core.personal_access_tokens.models import StoredPersonalAccessToken
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.personal_access_tokens.deps import get_personal_access_token_service
from umbod.rest.personal_access_tokens.models import CreatedPersonalAccessToken

pytestmark = pytest.mark.asyncio
URL = "/api/me/personal-access-tokens"


def creation_body() -> dict[str, object]:
    return {
        "name": "OTEL collector",
        "permissions": {"telemetry": "write"},
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


async def test_creation_reveals_secret_once_with_requested_effective_access(
    client: AsyncClient, runtime: PersistenceRuntime, caller: CallerContext
) -> None:
    response = await client.post(URL, json=creation_body())
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["metadata"]["audience"] == TELEMETRY_TOKEN_AUDIENCE
    assert body["metadata"]["scopes"] == [TELEMETRY_INGEST_SCOPE]
    assert body["metadata"]["owner"] == {
        "issuer": " https://issuer/ ",
        "subject": " Alice ",
    }
    assert body["token"] not in repr(CreatedPersonalAccessToken.model_validate(body))
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    validated = await service.validate(
        ValidatePersonalAccessToken(
            token=SecretStr(body["token"]),
            audience=TELEMETRY_TOKEN_AUDIENCE,
            required_scopes=(TELEMETRY_INGEST_SCOPE,),
        )
    )
    assert validated.token_id == body["metadata"]["token_id"]


async def test_revocation_removes_token_from_listing_and_repeated_delete_returns_not_found(
    client: AsyncClient, runtime: PersistenceRuntime
) -> None:
    created = (await client.post(URL, json=creation_body())).json()
    token_id = created["metadata"]["token_id"]
    assert (await client.delete(f"{URL}/{token_id}")).status_code == 204
    repeated = await client.delete(f"{URL}/{token_id}")
    missing = await client.delete(f"{URL}/{'0' * 32}")
    assert repeated.status_code == missing.status_code == 404
    assert repeated.json() == missing.json()
    listed = await client.get(URL)
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert listed.json() == []
    assert await DatabasePersonalAccessTokenStore(runtime.database).find(token_id) is None
    assert created["token"] not in listed.text
    assert "digest" not in listed.text
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(
            ValidatePersonalAccessToken(
                token=SecretStr(created["token"]),
                audience=TELEMETRY_TOKEN_AUDIENCE,
                required_scopes=(TELEMETRY_INGEST_SCOPE,),
            )
        )


async def test_legacy_revoked_token_can_be_deleted(
    client: AsyncClient, runtime: PersistenceRuntime
) -> None:
    created = (await client.post(URL, json=creation_body())).json()
    metadata = CreatedPersonalAccessToken.model_validate(created).metadata.model_copy(
        update={"token_id": "f" * 32, "status": PersonalAccessTokenStatus.REVOKED}
    )
    store = DatabasePersonalAccessTokenStore(runtime.database)
    assert await store.insert(StoredPersonalAccessToken(metadata=metadata, digest="0" * 64))
    assert metadata.model_dump(mode="json") in (await client.get(URL)).json()
    assert (await client.delete(f"{URL}/{metadata.token_id}")).status_code == 204
    assert await store.find(metadata.token_id) is None
    listed = (await client.get(URL)).json()
    assert listed == [created["metadata"]]
    assert (await client.delete(f"{URL}/{metadata.token_id}")).status_code == 404


@pytest.mark.parametrize("field", ["owner", "audience", "scopes"])
async def test_creation_forbids_caller_selected_authority(
    client: AsyncClient, field: str
) -> None:
    body = creation_body() | {field: "unapproved"}
    assert (await client.post(URL, json=body)).status_code == 422
    assert (await client.get(URL)).json() == []


@pytest.mark.parametrize(
    "updates",
    [
        {"name": ""},
        {"name": " "},
        {"name": "x" * 257},
        {"expires_at": "2030-01-01T00:00:00"},
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"expires_at": None},
    ],
)
async def test_creation_rejects_invalid_name_or_expiration(
    client: AsyncClient, updates: dict[str, object]
) -> None:
    assert (await client.post(URL, json=creation_body() | updates)).status_code == 422


async def test_creation_requires_explicit_expiration(client: AsyncClient) -> None:
    payload = creation_body()
    del payload["expires_at"]
    assert (await client.post(URL, json=payload)).status_code == 422


async def test_creation_requires_explicit_permissions(client: AsyncClient) -> None:
    payload = creation_body()
    del payload["permissions"]
    assert (await client.post(URL, json=payload)).status_code == 422
    assert (await client.get(URL)).json() == []


@pytest.mark.parametrize(
    "permissions",
    [
        {},
        None,
        [],
        {"unknown": "write"},
        {"telemetry": "read"},
        {"telemetry": "admin"},
        {"telemetry": "unknown"},
        {"telemetry": "*"},
        {"telemetry": ["write"]},
        {"*": "write"},
        {"/api/telemetry/v1/traces": "write"},
        {"https://example.test/api": "write"},
        {"telemetry": "write", "admin": "write"},
    ],
)
async def test_creation_rejects_unsupported_permissions(
    client: AsyncClient, permissions: object
) -> None:
    response = await client.post(
        URL, json=creation_body() | {"permissions": permissions}
    )
    assert response.status_code == 422
    assert (await client.get(URL)).json() == []


async def test_other_audience_tokens_are_listed_and_revoked(
    client: AsyncClient, runtime: PersistenceRuntime, caller: CallerContext
) -> None:
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    issued = await service.issue(
        caller,
        IssuePersonalAccessToken(
            name="other endpoint",
            audience="another:audience",
            scopes=(TELEMETRY_INGEST_SCOPE,),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )
    listed = await client.get(URL)
    assert listed.json() == [issued.metadata.model_dump(mode="json")]
    assert issued.token.get_secret_value() not in listed.text
    assert "digest" not in listed.text
    assert (await client.delete(f"{URL}/{issued.metadata.token_id}")).status_code == 204
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(
            ValidatePersonalAccessToken(
                token=issued.token,
                audience="another:audience",
                required_scopes=(TELEMETRY_INGEST_SCOPE,),
            )
        )


async def test_foreign_and_missing_ids_are_indistinguishable(
    client: AsyncClient, app: FastAPI, caller: CallerContext
) -> None:
    created = (await client.post(URL, json=creation_body())).json()

    def foreign_caller() -> CallerContext:
        return caller.model_copy(
            update={
                "subject": caller.subject.model_copy(update={"subject": "someone else"})
            }
        )

    app.dependency_overrides[get_caller_context] = foreign_caller
    assert (await client.get(URL)).json() == []
    foreign = await client.delete(f"{URL}/{created['metadata']['token_id']}")
    missing = await client.delete(f"{URL}/{'0' * 32}")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    del app.dependency_overrides[get_caller_context]
    assert len((await client.get(URL)).json()) == 1


@pytest.mark.parametrize(
    "method,path", [("GET", URL), ("POST", URL), ("DELETE", URL + "/missing")]
)
async def test_local_simulation_cannot_manage_tokens(
    client: AsyncClient, app: FastAPI, caller: CallerContext, method: str, path: str
) -> None:
    def simulated_caller() -> CallerContext:
        return caller.model_copy(
            update={"authentication": AuthenticationProvenance.LOCAL_SIMULATION}
        )

    app.dependency_overrides[get_caller_context] = simulated_caller
    response = await client.request(method, path, json=creation_body())
    assert response.status_code == 403


async def test_missing_verified_caller_is_unauthorized(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(URL)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,operation",
    [
        ("GET", URL, "list_tokens"),
        ("POST", URL, "issue"),
        ("DELETE", URL + "/missing", "revoke"),
    ],
)
async def test_persistence_failure_returns_sanitized_service_unavailable(
    client: AsyncClient,
    app: FastAPI,
    runtime: PersistenceRuntime,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    operation: str,
) -> None:
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    monkeypatch.setattr(
        service, operation, AsyncMock(side_effect=RuntimeError("credential-secret"))
    )

    def failing_service() -> PersonalAccessTokenService:
        return service

    app.dependency_overrides[get_personal_access_token_service] = failing_service
    response = await client.request(method, path, json=creation_body())
    assert response.status_code == 503
    assert "credential-secret" not in response.text
    assert "token" not in response.json()


async def test_revocation_does_not_read_owner_listing(
    client: AsyncClient,
    app: FastAPI,
    runtime: PersistenceRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = (await client.post(URL, json=creation_body())).json()
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    listing = AsyncMock(side_effect=RuntimeError("listing must not be read"))
    monkeypatch.setattr(service, "list_tokens", listing)

    def token_service() -> PersonalAccessTokenService:
        return service

    app.dependency_overrides[get_personal_access_token_service] = token_service
    response = await client.delete(f"{URL}/{created['metadata']['token_id']}")
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    listing.assert_not_awaited()


async def test_failed_revoke_does_not_acknowledge_success(
    client: AsyncClient,
    app: FastAPI,
    runtime: PersistenceRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = (await client.post(URL, json=creation_body())).json()
    service = create_personal_access_token_service(
        runtime.database, personal_access_token_policy()
    )
    monkeypatch.setattr(
        service, "revoke", AsyncMock(side_effect=RuntimeError("credential-secret"))
    )

    def failing_service() -> PersonalAccessTokenService:
        return service

    app.dependency_overrides[get_personal_access_token_service] = failing_service
    response = await client.delete(f"{URL}/{created['metadata']['token_id']}")
    assert response.status_code == 503
    assert "credential-secret" not in response.text
    assert (await client.get(URL)).json()[0]["status"] == "active"


async def test_database_readiness_failure_is_sanitized(
    client: AsyncClient,
    runtime: PersistenceRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime.readiness,
        "ensure_ready",
        AsyncMock(side_effect=RuntimeError("credential-secret")),
    )
    response = await client.get(URL)
    assert response.status_code == 503
    assert "credential-secret" not in response.text
