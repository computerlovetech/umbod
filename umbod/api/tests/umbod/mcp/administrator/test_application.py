from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from typing import Any
from unittest.mock import AsyncMock

import httpx2
import jwt
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from jsonschema import Draft202012Validator
from mcp.types import Tool
from starlette.applications import Starlette

from tests.mcp_telemetry_fixtures import RecordingApplicationMetricsRecorder, RecordingAuditSink, RecordingMetricsServerFactory
from umbod.config import AppConfig
from umbod.core.administrator.connector_configuration.service import AdministratorConnectorConfigurationService
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.logging import create_application_failure_signal
from umbod.mcp.administrator.application import build_administrator_app
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.runtime_options import ConnectorRuntimeOptions, resolve_connector_runtime
from umbod.mcp.telemetry import McpTelemetryDependencies

ADMIN_TOOLS = {"admin_discover", "admin_inspect", "admin_apply"}
CONNECTOR = {"connector_kind": "native", "connector_id": "existing"}
INSPECT_MISSING = {
    "operation": "read_connector_configuration",
    "connector": {"connector_kind": "native", "connector_id": "missing"},
}
NAMESPACE_ID = "894ab745-8260-49c4-9e73-cb35dab8e639"


def update_connector(operations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "operation": "update_connector_configuration",
        "connector": CONNECTOR,
        "desired_state": {"operations": operations},
    }


def policy_operation(kind: str) -> dict[str, Any]:
    return {
        "operation": "set_capability_invocation_policy", "capability_kind": kind,
        "capability_key": "lookup", "mode": "ask", "expected_revision": 0,
    }


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
        result = await client.call_tool("admin_inspect", {"request": INSPECT_MISSING}, raise_on_error=False)
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
        result = await client.call_tool("admin_inspect", {"request": INSPECT_MISSING}, raise_on_error=False)
        assert result.is_error


@pytest_asyncio.fixture
async def descriptors(telemetry: McpTelemetryDependencies) -> dict[str, Tool]:
    settings = application_settings()
    async with application(settings, telemetry) as app, Client(transport(app, settings.mcp.test_bearer_token)) as client:
        return {tool.name: tool for tool in await client.list_tools()}


@pytest.mark.parametrize(
    "tool_name, valid_requests",
    [
        ("admin_discover", (
            {"operation": "list_connectors"},
            {"operation": "list_groups"},
            {"operation": "list_permission_targets"},
            {"operation": "search_users", "query": "Ada", "limit": 1},
            {"operation": "list_namespaces"},
        )),
        ("admin_inspect", (
            {"operation": "read_connector_configuration", "connector": CONNECTOR},
            {"operation": "read_group_permissions", "group_id": " Team "},
        )),
        ("admin_apply", (
            {"operation": "update_connector_configuration", "connector": CONNECTOR, "desired_state": {}},
            {"operation": "update_group_permissions", "group_id": "engineering", "connectors": [
                {"connector_id": "existing", "permission_status": "enabled"},
            ]},
            {"operation": "create_namespace", "namespace": {"name": "Shared", "groups": []}},
            {"operation": "update_namespace", "namespace_id": NAMESPACE_ID,
             "namespace": {"name": "Shared", "groups": [], "expected_revision": 1}},
        )),
    ],
)
def test_tools_list_publishes_independently_usable_operation_branches(
    descriptors: dict[str, Tool], tool_name: str, valid_requests: tuple[dict[str, Any], ...],
) -> None:
    descriptor = descriptors[tool_name]
    schema = descriptor.input_schema
    validator = Draft202012Validator(schema)
    assert "request" in schema["required"]
    branches = {
        branch["properties"]["operation"]["const"]: branch
        for branch in schema["properties"]["request"]["oneOf"]
    }
    assert set(branches) == {request["operation"] for request in valid_requests}
    for request in valid_requests:
        branch = branches[request["operation"]]
        assert branch["type"] == "object"
        assert "operation" in branch["required"]
        Draft202012Validator(branch).validate(request)
        validator.validate({"request": request})
        assert not validator.is_valid({"request": {**request, "unexpected": True}})
        assert not validator.is_valid({"request": {**request, "operation": "unknown"}})
        for required in branch["required"]:
            assert not validator.is_valid({"request": {key: value for key, value in request.items() if key != required}})


@pytest.mark.parametrize("connector_id", [None, ""])
def test_tools_list_requires_nonempty_nested_connector_ids(
    descriptors: dict[str, Tool], connector_id: str | None,
) -> None:
    for tool_name, request in (
        ("admin_inspect", INSPECT_MISSING),
        ("admin_apply", update_connector([])),
    ):
        connector = {"connector_kind": "native"}
        if connector_id is not None:
            connector["connector_id"] = connector_id
        assert not Draft202012Validator(descriptors[tool_name].input_schema).is_valid(
            {"request": {**request, "connector": connector}},
        )


@pytest.mark.parametrize("kind", ["tool", "prompt", "resource", "resource_template"])
def test_tools_list_limits_policy_to_tools_without_narrowing_other_capability_kinds(
    descriptors: dict[str, Tool], kind: str,
) -> None:
    validator = Draft202012Validator(descriptors["admin_apply"].input_schema)
    policy = policy_operation(kind)
    activation = {
        "operation": "set_capability_activation", "capability_kind": kind,
        "capability_key": "lookup", "activation_status": "enabled",
    }
    permission = {
        "operation": "update_group_permissions", "group_id": "engineering",
        "capabilities": [{"capability_kind": kind, "capability_key": "lookup", "status": "enabled"}],
    }
    assert validator.is_valid({"request": update_connector([policy])}) == (kind == "tool")
    validator.validate({"request": update_connector([activation, permission])})


@pytest.mark.parametrize(
    "changes, valid",
    [
        ({}, True),
        ({"description": "", "expected_root_revision": 2}, True),
        ({"description": ""}, False),
        ({"expected_root_revision": 2}, False),
        ({"description": "", "expected_root_revision": 0}, False),
        ({"groups": [{"group_id": "engineering", "access": "write"}]}, False),
    ],
)
def test_tools_list_publishes_both_namespace_update_shapes(
    descriptors: dict[str, Tool], changes: dict[str, Any], valid: bool,
) -> None:
    request = {
        "operation": "update_namespace", "namespace_id": NAMESPACE_ID,
        "namespace": {"name": "Shared", "groups": [], "expected_revision": 1, **changes},
    }
    assert Draft202012Validator(descriptors["admin_apply"].input_schema).is_valid({"request": request}) == valid


def test_tools_list_explains_update_semantics(descriptors: dict[str, Tool]) -> None:
    descriptor = descriptors["admin_apply"]
    guidance = json.dumps(descriptor.input_schema) + descriptor.description
    for instruction in (
        "omitted or empty operations read the current configuration without changes",
        "Do not repeat a target within an operation type",
        "combine description override and restore",
        "one permission patch per group",
        "at least one connector or capability change",
        "full replacement list of group grants",
        "empty string clears it",
        "inspect current state before retrying",
    ):
        assert instruction in guidance


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["admin_inspect", "admin_apply"])
@pytest.mark.parametrize("connector_id", [None, ""])
async def test_invalid_connector_identifiers_are_rejected_before_service_admission(
    tool_name: str, connector_id: str | None,
    telemetry: McpTelemetryDependencies, monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = AsyncMock()
    upsert = AsyncMock()
    monkeypatch.setattr(AdministratorConnectorConfigurationService, "read", read)
    monkeypatch.setattr(AdministratorConnectorConfigurationService, "upsert", upsert)
    connector = {"connector_kind": "native"}
    if connector_id is not None:
        connector["connector_id"] = connector_id
    operation = INSPECT_MISSING if tool_name == "admin_inspect" else update_connector([])
    settings = application_settings()
    async with application(settings, telemetry) as app, Client(transport(app, settings.mcp.test_bearer_token)) as client:
        result = await client.call_tool(tool_name, {"request": {**operation, "connector": connector}}, raise_on_error=False)
    assert result.is_error
    read.assert_not_awaited()
    upsert.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("capability_kind", ["prompt", "resource", "resource_template"])
async def test_non_tool_policy_calls_are_rejected_before_mutations(
    capability_kind: str, telemetry: McpTelemetryDependencies, monkeypatch: pytest.MonkeyPatch,
) -> None:
    upsert = AsyncMock()
    monkeypatch.setattr(AdministratorConnectorConfigurationService, "upsert", upsert)
    settings = application_settings()
    request = update_connector([
        {"operation": "set_capability_activation", "capability_kind": "tool", "capability_key": "lookup", "activation_status": "disabled"},
        policy_operation(capability_kind),
    ])
    async with application(settings, telemetry) as app, Client(transport(app, settings.mcp.test_bearer_token)) as client:
        result = await client.call_tool("admin_apply", {"request": request}, raise_on_error=False)
    assert result.is_error
    upsert.assert_not_awaited()


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
