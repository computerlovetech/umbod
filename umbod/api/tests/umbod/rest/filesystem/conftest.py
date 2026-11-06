from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware import Middleware
from starlette.routing import Mount

from umbod.config import AppConfig, InMemoryConnectorStoreConfig, PersistenceConfig, SQLiteConnectorStoreConfig
from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.filesystem import Permission, Principal, PrincipalType, RootBootstrapGrant, RootBootstrapSpec
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider, create_root_provisioning
from umbod.rest.authentication.csrf_middleware import RestCookieCsrfMiddleware
from umbod.rest.authentication.middleware import JwtVerifierFactory, SuppliedJwtVerifierFactory
from umbod.rest.authentication.rest_middleware import RestAuthenticationMiddleware
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories, LifespanRootApiAppFactory, SubApiAppFactory
from umbod.rest.filesystem.upload_transfers import router as filesystem_transfer_router
from umbod.rest.main import _attach_dependency_factories, _mount_personal_connections_app, create_app


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


@pytest.fixture
def filesystem_upload_max_bytes(request: pytest.FixtureRequest) -> int:
    return getattr(request, "param", 10 * 1024 * 1024)


@pytest.fixture
def filesystem_persistence_config(request: pytest.FixtureRequest) -> PersistenceConfig:
    if getattr(request, "param", "inmemory") == "sqlite":
        database_path = cast(Path, request.getfixturevalue("isolated_connector_store_database"))
        return SQLiteConnectorStoreConfig(sqlite_path=str(database_path))
    return InMemoryConnectorStoreConfig()


@pytest.fixture(scope="session")
def filesystem_deployment_configuration(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("filesystem-deployment") / "deployment.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    return path


@pytest.fixture
def filesystem_settings(
    filesystem_deployment_configuration: Path, monkeypatch: pytest.MonkeyPatch,
    filesystem_upload_max_bytes: int, filesystem_persistence_config: PersistenceConfig,
    filesystem_personal_enabled: bool,
) -> AppConfig:
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(filesystem_deployment_configuration),
    )
    return AppConfig(
        rest={"metrics_enabled": False},
        filesystem={"upload_max_bytes": filesystem_upload_max_bytes},
        connector_store=filesystem_persistence_config,
        personal_connections={"enabled": filesystem_personal_enabled, "identity_namespace": "test:filesystem"},
        mcp={"permission_group_claim": "filesystem_groups"},
    )


@pytest.fixture(params=[False, True], ids=["personal-disabled", "personal-enabled"])
def filesystem_personal_enabled(request: pytest.FixtureRequest) -> bool:
    return request.param


def _create_filesystem_app(settings: AppConfig) -> FastAPI:
    settings.validate_rest_authentication()
    runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, [])
    factories.validate_startup()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        try:
            await runtime.readiness.ensure_ready()
            yield {}
        finally:
            await runtime.shutdown()

    root = LifespanRootApiAppFactory(settings, lifespan).create()
    _mount_personal_connections_app(root, settings, factories)
    transfer_app = SubApiAppFactory(
        title="umbod-filesystem-transfer-api", router=filesystem_transfer_router,
    ).create()
    _attach_dependency_factories(transfer_app, factories)
    root.mount("/api/filesystem", transfer_app)
    root.user_middleware.extend([
        Middleware(
            RestCookieCsrfMiddleware,
            site_base_url=settings.endpoints.site_base_url,
            allowed_origins=settings.cors.origins,
        ),
        Middleware(
            RestAuthenticationMiddleware, settings=settings,
            admin_verifier_factory=JwtVerifierFactory(),
            user_verifier_factory=SuppliedJwtVerifierFactory(AcceptedTestVerifier()),
        ),
    ])
    return root


@contextmanager
def _filesystem_client(root: FastAPI) -> Iterator[FilesystemHttp]:
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
        assert client.get("/api/me/filesystem/browse").status_code == 403
        factories = captured[-1]
        provisioner = create_root_provisioning(database=factories.persistence_runtime.database)
        client.portal.call(provisioner.provision, RootBootstrapSpec(grants=(
            RootBootstrapGrant(
                principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
                permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
            ),
        )))
        yield FilesystemHttp(client, app, root, factories)


@pytest.fixture
def filesystem_http(filesystem_settings: AppConfig) -> Iterator[FilesystemHttp]:
    with _filesystem_client(_create_filesystem_app(filesystem_settings)) as http:
        yield http


@pytest.fixture
def filesystem_full_http(filesystem_settings: AppConfig) -> Iterator[FilesystemHttp]:
    root = create_app(filesystem_settings, [], user_verifier=AcceptedTestVerifier())
    with _filesystem_client(root) as http:
        yield http
