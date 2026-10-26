from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.filesystem import Permission, Principal, PrincipalType, RootBootstrapGrant, RootBootstrapSpec
from umbod.infrastructure import create_root_provisioning
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app


class AcceptedTestVerifier:
    def verify(self, token: str) -> JwtClaims:
        if token not in ("alice", "bob", "outsider", "blank"):
            raise JwtVerificationError()
        return JwtClaims(claims={
            "iss": "issuer", "sub": token,
            "filesystem_groups": ["team", "team", 42] if token != "outsider" else [],
            "groups": ["wrong-claim"],
        })


@dataclass
class FilesystemHttp:
    client: TestClient
    app: FastAPI
    root: FastAPI
    factories: ConnectorApiDependencyFactories


@pytest.fixture(params=[False, True], ids=["personal-disabled", "personal-enabled"])
def filesystem_http(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[FilesystemHttp]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "filesystem.sqlite")},
        personal_connections={"enabled": request.param, "identity_namespace": "test:filesystem"},
        mcp={"permission_group_claim": "filesystem_groups"},
    )
    root = create_app(settings, [], user_verifier=AcceptedTestVerifier())
    app = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == "/api/me")
    captured: list[ConnectorApiDependencyFactories] = []

    def capture_factories(request: Request) -> ConnectorApiDependencyFactories:
        factories = get_connector_api_dependency_factories(request)
        captured.append(factories)
        return factories

    def trusted_test_caller(request: Request) -> CallerContext:
        return get_caller_context(request).model_copy(update={
            "authentication": AuthenticationProvenance.UPSTREAM_VERIFIED,
        })

    app.dependency_overrides[get_connector_api_dependency_factories] = capture_factories
    app.dependency_overrides[get_caller_context] = trusted_test_caller
    with TestClient(root, headers={"Authorization": "Bearer alice"}) as client:
        assert client.get("/api/me/filesystem/root").status_code == 403
        factories = captured[-1]
        provisioner = create_root_provisioning(database=factories.persistence_runtime.database)
        client.portal.call(provisioner.provision, RootBootstrapSpec(grants=(
            RootBootstrapGrant(
                principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
                permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
            ),
        )))
        yield FilesystemHttp(client, app, root, factories)
