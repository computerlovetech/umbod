from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import httpx2
import jwt
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.applications import Starlette

from tests.mcp_telemetry_fixtures import RecordingApplicationMetricsRecorder, RecordingAuditSink, RecordingMetricsServerFactory
from umbod.config import AppConfig
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.logging import create_application_failure_signal
from umbod.mcp.administrator.application import build_administrator_app
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.runtime_options import ConnectorRuntimeOptions, resolve_connector_runtime
from umbod.mcp.telemetry import McpTelemetryDependencies

ADMIN_TOOLS = {'read_connector_configuration', 'upsert_connector_configuration'}


def application_settings(*, administrator: bool = True, enabled: bool = True) -> AppConfig:
    token = jwt.encode(
        {'sub': 'caller', 'email': 'caller@example.test', 'groups': ['administrators'] if administrator else ['engineering']},
        key='', algorithm='none',
    )
    return AppConfig(
        connector_store={'type': 'inmemory'},
        mcp={'auth_mode': 'single_test_user', 'test_bearer_token': token, 'stateless_http': True, 'metrics_enabled': True},
        mcp_administrator={'hosting': 'separate', 'base_url': 'https://administrator.example.test'},
        endpoints={'mcp_base_url': 'http://public.example.test'},
        admin_authentication={'membership_claim': 'groups', 'required_membership': 'administrators'},
        feature_toggles={'mcp_administrator_enabled': enabled},
        connector_security={'configuration_secret': 'test-administrator-configuration-secret'},
    )


@pytest.fixture
def telemetry() -> McpTelemetryDependencies:
    failures = create_application_failure_signal()
    return McpTelemetryDependencies(
        audit_recorder=McpAuditRecorder(RecordingAuditSink(), 'administrator', failures),
        metrics_recorder=RecordingApplicationMetricsRecorder(),
        invocation_log_sink=InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        metrics_server_factory=RecordingMetricsServerFactory(),
        application_failures=failures,
    )


@asynccontextmanager
async def application(settings: AppConfig, telemetry: McpTelemetryDependencies) -> AsyncIterator[Starlette]:
    persistence = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    try:
        runtime = await resolve_connector_runtime(settings, ConnectorRuntimeOptions(connector_registrations=[]), persistence)
        app = await build_administrator_app(settings, runtime, persistence, telemetry=telemetry)
        async with app.router.lifespan_context(app):
            yield app
        await persistence.readiness.ensure_ready()
    finally:
        await persistence.shutdown()


def transport(app: Starlette, token: str) -> StreamableHttpTransport:
    def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **kwargs)

    return StreamableHttpTransport(
        'https://administrator.example.test/mcp', headers={'Authorization': f'Bearer {token}'},
        httpx_client_factory=create_http_client,
    )


@pytest.mark.asyncio
async def test_dedicated_application_exposes_only_administrator_tools(telemetry: McpTelemetryDependencies) -> None:
    settings = application_settings()
    async with application(settings, telemetry) as app, Client(transport(app, settings.mcp.test_bearer_token)) as client:
        assert {tool.name for tool in await client.list_tools()} == ADMIN_TOOLS
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []
        assert await client.list_prompts() == []
        result = await client.call_tool(
            'read_connector_configuration', {'connector_kind': 'native', 'connector_id': 'missing'}, raise_on_error=False,
        )
        assert result.is_error
        assert 'computerlove.tech/umbod' in result.meta
    assert telemetry.metrics_recorder.protocol_requests
    assert telemetry.metrics_recorder.invocations
    assert telemetry.metrics_server_factory.servers == []


@pytest.mark.asyncio
@pytest.mark.parametrize('administrator,enabled', [(False, True), (True, False)])
async def test_unavailable_administrator_tools_cannot_be_called(
    administrator: bool, enabled: bool, telemetry: McpTelemetryDependencies,
) -> None:
    settings = application_settings(administrator=administrator, enabled=enabled)
    async with application(settings, telemetry) as app, Client(transport(app, settings.mcp.test_bearer_token)) as client:
        assert await client.list_tools() == []
        result = await client.call_tool(
            'read_connector_configuration', {'connector_kind': 'native', 'connector_id': 'missing'}, raise_on_error=False,
        )
        assert result.is_error


@pytest.mark.asyncio
async def test_dedicated_health_and_oauth_metadata_use_own_endpoint(telemetry: McpTelemetryDependencies) -> None:
    settings = application_settings()
    async with application(settings, telemetry) as app, httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url='https://administrator.example.test',
    ) as client:
        health = await client.get('/system/health')
        assert health.status_code == 200
        assert health.json() == {'status': 'ok'}
        metadata = await client.get('/.well-known/oauth-authorization-server')
        assert metadata.status_code == 200
        assert metadata.json()['issuer'] == 'https://administrator.example.test/'
        assert metadata.json()['authorization_endpoint'].startswith('https://administrator.example.test/')
    assert settings.endpoints.mcp_base_url == 'http://public.example.test'


@pytest.mark.asyncio
@pytest.mark.parametrize('authorization', ['', 'Bearer invalid-administrator-token'])
async def test_administrator_transport_requires_valid_authentication(
    authorization: str, telemetry: McpTelemetryDependencies,
) -> None:
    settings = application_settings()
    headers = {'Accept': 'application/json, text/event-stream'}
    if authorization:
        headers['Authorization'] = authorization
    async with application(settings, telemetry) as app, httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url='https://administrator.example.test',
    ) as client:
        response = await client.post(
            '/mcp', headers=headers,
            json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
        )
        assert response.status_code == 401
        assert 'https://administrator.example.test/' in response.headers['www-authenticate']


@pytest.mark.asyncio
async def test_administrator_lifespan_does_not_close_caller_persistence(
    telemetry: McpTelemetryDependencies, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = application_settings()
    persistence = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    shutdown = AsyncMock(wraps=persistence.shutdown)
    monkeypatch.setattr(type(persistence), 'shutdown', shutdown)
    try:
        runtime = await resolve_connector_runtime(settings, ConnectorRuntimeOptions(connector_registrations=[]), persistence)
        app = await build_administrator_app(settings, runtime, persistence, telemetry=telemetry)
        async with app.router.lifespan_context(app):
            pass
        shutdown.assert_not_awaited()
    finally:
        await persistence.shutdown()
