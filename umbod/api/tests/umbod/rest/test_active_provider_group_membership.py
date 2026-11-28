import json
from collections.abc import Iterator, Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from time import time
from typing import Annotated

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.routing import Mount

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import load_app_config_without_env_file
from umbod.core.callers import AuthenticationProvenance, CallerContext, CallerSnapshot, DeclaredIssuer, GroupMembership, SubjectIdentity
from umbod.core.callers.membership import GroupMembershipResolver
from umbod.core.connectors.downstream_mcp.personal.connections import PersonalCaller
from umbod.core.persistence import ReadSession
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.authentication.membership import RequestCallerSnapshot
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.connectors.downstream_mcp.personal_connections.dependencies import get_personal_caller
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.filesystem.deps import get_filesystem_caller
from umbod.rest.main import create_app_with_dependency_factories
from umbod.rest.user_catalogue.caller import CatalogueCaller, get_catalogue_caller

_ISSUER = "https://identity.example/"
_LOCAL_GROUP = "engineering"
_EXTERNAL_GROUP = "external-engineering"
_ADMIN_GROUP = "application-administrators"
_PERMISSION_CLAIM = "https://identity.example/teams"
_MAPPINGS = "/api/admin/system-settings/provider-group-mappings"
_SUBJECT = "auth0|person"
_PROJECTION = "/api/me/caller-projection"
_RULE = {"external_value": _EXTERNAL_GROUP}


class CapturedCallers(BaseModel):
    filesystem: CallerSnapshot
    personal: PersonalCaller
    catalogue: CatalogueCaller

    @property
    def group_ids(self) -> tuple[tuple[str, ...], ...]:
        return (self.filesystem.groups.group_ids, self.personal.groups.group_ids, self.catalogue.groups.group_ids)


def _project_callers(
    filesystem: Annotated[CallerSnapshot, Depends(get_filesystem_caller)],
    personal: Annotated[PersonalCaller, Depends(get_personal_caller)],
    catalogue: Annotated[CatalogueCaller, Depends(get_catalogue_caller)],
    snapshot: RequestCallerSnapshot,
) -> CapturedCallers:
    if isinstance(snapshot, CallerSnapshot):
        assert filesystem is snapshot
        assert personal.caller is catalogue.caller is snapshot.caller
        assert personal.groups is catalogue.groups is snapshot.groups
    return CapturedCallers(filesystem=filesystem, personal=personal, catalogue=catalogue)


@pytest.fixture
def factories(
    monkeypatch: pytest.MonkeyPatch,
) -> ConnectorApiDependencyFactories:
    environment = {
        "UMBOD_PROFILE": "production",
        "UMBOD_AUTH": "auth0",
        "UMBOD_ROOT_SECRET": "provider-mapping-test-root-secret",
        "UMBOD_OIDC_DOMAIN": "identity.example",
        "UMBOD_OIDC_ISSUER_URL": "",
        "UMBOD_OIDC_CLIENT_ID": "rest-client",
        "UMBOD_OIDC_CLIENT_SECRET": "rest-secret",
        "UMBOD_OIDC_AUDIENCE": "api",
        "UMBOD_ADMIN_JWT_HEADER_NAME": "Authorization",
        "UMBOD_ADMIN_MEMBERSHIP_CLAIM": "roles",
        "UMBOD_ADMIN_GROUP": _ADMIN_GROUP,
        "UMBOD_MCP_PERMISSION_CLAIM": _PERMISSION_CLAIM,
        "UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE": "example",
        "UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED": "false",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    settings = load_app_config_without_env_file()
    settings.rest.metrics_enabled = False
    return ConnectorApiDependencyFactories.from_settings(settings, create_inmemory_runtime(), ())


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def app(
    factories: ConnectorApiDependencyFactories,
    signing_key: rsa.RSAPrivateKey,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    verifier = ProductionJwksJwtVerifier(_ISSUER + "jwks", _ISSUER, "api")
    public_key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public_key["kid"] = "group-membership"
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [public_key]})
    application = create_app_with_dependency_factories(factories, admin_verifier=verifier, user_verifier=verifier)
    _personal_app(application).add_api_route("/caller-projection", _project_callers, methods=["GET"])
    return application


def _personal_app(app: FastAPI) -> FastAPI:
    personal = next(route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/me")
    assert isinstance(personal, FastAPI)
    return personal


def _headers(signing_key: rsa.RSAPrivateKey, subject: str, claims: dict[str, object]) -> dict[str, str]:
    token = jwt.encode(
        {"iss": _ISSUER, "sub": subject, "aud": "api", "exp": int(time()) + 600, **claims},
        signing_key, algorithm="RS256", headers={"kid": "group-membership"},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(signing_key: rsa.RSAPrivateKey) -> dict[str, str]:
    return _headers(signing_key, "admin", {"roles": [_ADMIN_GROUP]})


@pytest.fixture
def user_headers(signing_key: rsa.RSAPrivateKey) -> dict[str, str]:
    return _headers(signing_key, _SUBJECT, {_PERMISSION_CLAIM: [_LOCAL_GROUP, _EXTERNAL_GROUP]})


@pytest.fixture
def client(app: FastAPI, admin_headers: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(app) as client:
        assert client.post("/api/admin/groups", json={"group_id": _LOCAL_GROUP}, headers=admin_headers).status_code == 204
        yield client


def _projection(client: TestClient, headers: dict[str, str]) -> CapturedCallers:
    response = client.get(_PROJECTION, headers=headers)
    assert response.status_code == 200, response.text
    return CapturedCallers.model_validate(response.json())


def _set_mapping(client: TestClient, headers: dict[str, str], group_id: str) -> None:
    response = client.patch(
        _MAPPINGS, headers=headers, json={"operation": "set", "mappings": [{**_RULE, "group_id": group_id}]},
    )
    assert response.status_code == 200, response.text


def test_saved_mapping_enables_ordinary_membership_without_changing_caller_identities(
    client: TestClient, admin_headers: dict[str, str], user_headers: dict[str, str],
) -> None:
    before = _projection(client, user_headers)
    assert before.group_ids == ((),) * 3
    assert before.filesystem.caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED
    _set_mapping(client, admin_headers, _LOCAL_GROUP)

    mapped = _projection(client, user_headers)

    assert mapped.group_ids == ((_LOCAL_GROUP,),) * 3
    assert mapped.filesystem.caller == before.filesystem.caller
    assert mapped.personal.principal == before.personal.principal
    assert mapped.catalogue.identity_key == before.catalogue.identity_key
    assert mapped.catalogue.personal_identity == before.catalogue.personal_identity


def test_admin_claim_cannot_supply_an_ordinary_membership_and_mapping_cannot_grant_admin(
    client: TestClient, admin_headers: dict[str, str], signing_key: rsa.RSAPrivateKey,
) -> None:
    _register_response = client.post("/api/admin/groups", json={"group_id": _ADMIN_GROUP}, headers=admin_headers)
    assert _register_response.status_code == 204
    _set_mapping(client, admin_headers, _ADMIN_GROUP)
    ordinary_member = _headers(signing_key, _SUBJECT, {_PERMISSION_CLAIM: [_EXTERNAL_GROUP]})
    other_claim_member = _headers(signing_key, _SUBJECT, {"roles": [_ADMIN_GROUP + "-other", _EXTERNAL_GROUP]})

    assert _projection(client, ordinary_member).group_ids == ((_ADMIN_GROUP,),) * 3
    assert client.get(_MAPPINGS, headers=ordinary_member).status_code == 403
    assert _projection(client, other_claim_member).group_ids == ((),) * 3
    assert _projection(client, admin_headers).group_ids == ((),) * 3


def test_mapping_is_not_applied_to_a_token_with_an_unverified_issuer(
    client: TestClient, admin_headers: dict[str, str], signing_key: rsa.RSAPrivateKey,
) -> None:
    _set_mapping(client, admin_headers, _LOCAL_GROUP)
    wrong_issuer = _headers(signing_key, _SUBJECT, {
        "iss": "https://other.example/", _PERMISSION_CLAIM: [_EXTERNAL_GROUP],
    })

    assert client.get(_PROJECTION, headers=wrong_issuer).status_code == 401
    assert client.get(_PROJECTION).status_code == 401


def test_null_target_is_rejected_without_changing_active_membership(
    client: TestClient, admin_headers: dict[str, str], user_headers: dict[str, str],
) -> None:
    _set_mapping(client, admin_headers, _LOCAL_GROUP)

    response = client.patch(
        _MAPPINGS, headers=admin_headers, json={"operation": "set", "mappings": [{**_RULE, "group_id": None}]},
    )

    assert response.status_code == 422
    assert _projection(client, user_headers).group_ids == ((_LOCAL_GROUP,),) * 3


def test_empty_save_and_reset_both_clear_verified_membership(
    client: TestClient, admin_headers: dict[str, str], user_headers: dict[str, str],
) -> None:
    _set_mapping(client, admin_headers, _LOCAL_GROUP)
    assert _projection(client, user_headers).group_ids == ((_LOCAL_GROUP,),) * 3

    assert client.patch(_MAPPINGS, headers=admin_headers, json={"operation": "set", "mappings": []}).status_code == 200
    assert _projection(client, user_headers).group_ids == ((),) * 3

    _set_mapping(client, admin_headers, _LOCAL_GROUP)
    assert client.patch(_MAPPINGS, headers=admin_headers, json={"operation": "reset"}).status_code == 200
    assert _projection(client, user_headers).group_ids == ((),) * 3


def test_verified_rest_callers_share_one_membership_resolution_per_request(
    client: TestClient, factories: ConnectorApiDependencyFactories, admin_headers: dict[str, str],
    signing_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapped_groups = ("design", "operations")
    for group_id in reversed(mapped_groups):
        assert client.post("/api/admin/groups", json={"group_id": group_id}, headers=admin_headers).status_code == 204
    response = client.patch(_MAPPINGS, headers=admin_headers, json={
        "operation": "set",
        "mappings": [{"external_value": group_id.upper(), "group_id": group_id} for group_id in reversed(mapped_groups)],
    })
    assert response.status_code == 200, response.text
    user_headers = _headers(signing_key, _SUBJECT, {_PERMISSION_CLAIM: ["OPERATIONS", _LOCAL_GROUP, "DESIGN", "DESIGN"]})
    source = factories.group_membership_source
    capture = source.capture
    resolve_verified = GroupMembershipResolver.resolve_verified
    captured: list[GroupMembershipResolver] = []
    resolved: list[GroupMembershipResolver] = []

    async def observe_capture() -> GroupMembershipResolver:
        resolver = await capture()
        captured.append(resolver)
        return resolver

    def observe_resolution(resolver: GroupMembershipResolver, claims: Mapping[str, object]) -> GroupMembership:
        resolved.append(resolver)
        return resolve_verified(resolver, claims)

    monkeypatch.setattr(source, "capture", observe_capture)
    monkeypatch.setattr(GroupMembershipResolver, "resolve_verified", observe_resolution)

    assert client.get("/api/admin/openapi.json", headers=admin_headers).status_code == 200
    assert not captured and not resolved
    for request_count in (1, 2):
        assert _projection(client, user_headers).group_ids == (mapped_groups,) * 3
        assert len(captured) == len(resolved) == request_count
        assert resolved[-1] is captured[-1]


def test_nonverified_caller_uses_legacy_membership_without_reading_mappings(
    app: FastAPI, client: TestClient, factories: ConnectorApiDependencyFactories,
    admin_headers: dict[str, str], user_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_mapping(client, admin_headers, _LOCAL_GROUP)

    def deployment_caller() -> CallerContext:
        return CallerContext(
            authentication=AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=_ISSUER), subject=_SUBJECT),
        )

    async def fail_capture() -> GroupMembershipResolver:
        pytest.fail("A nonverified caller must not read provider group mappings")

    _personal_app(app).dependency_overrides[get_caller_context] = deployment_caller
    monkeypatch.setattr(factories.group_membership_source, "capture", fail_capture)

    assert _projection(client, user_headers).group_ids == ((_LOCAL_GROUP, _EXTERNAL_GROUP),) * 3


def test_unavailable_mapping_read_denies_verified_groups_without_breaking_admin_authentication(
    client: TestClient, factories: ConnectorApiDependencyFactories,
    admin_headers: dict[str, str], user_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read() -> AbstractAsyncContextManager[ReadSession]:
        raise OSError("Provider mapping storage unavailable")

    monkeypatch.setattr(factories.persistence_runtime.database, "read_session", fail_read)

    assert _projection(client, user_headers).group_ids == ((),) * 3
    assert client.get("/api/admin/openapi.json", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/openapi.json", headers=user_headers).status_code == 403
