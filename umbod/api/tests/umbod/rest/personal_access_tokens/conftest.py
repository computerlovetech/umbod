from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from tests.persistence_runtime import create_inmemory_runtime
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.authentication.deps import CALLER_CONTEXT_STATE_KEY
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.settings import APISettings
from umbod.rest.personal_access_tokens import router


@pytest_asyncio.fixture
async def runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = create_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@pytest.fixture
def app(runtime: PersistenceRuntime) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/me")
    factories = ConnectorApiDependencyFactories.from_settings(
        APISettings(connector_store={"type": "inmemory"}), runtime, []
    )

    def get_factories() -> ConnectorApiDependencyFactories:
        return factories

    app.dependency_overrides[get_connector_api_dependency_factories] = get_factories
    return app


@pytest.fixture
def caller() -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value=" https://issuer/ "), subject=" Alice "
        ),
    )


@pytest_asyncio.fixture
async def client(app: FastAPI, caller: CallerContext) -> AsyncIterator[AsyncClient]:
    @app.middleware("http")
    async def supply_caller(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        setattr(request.state, CALLER_CONTEXT_STATE_KEY, caller)
        return await call_next(request)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
