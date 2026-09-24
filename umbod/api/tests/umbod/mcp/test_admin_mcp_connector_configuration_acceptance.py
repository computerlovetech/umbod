from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx2
import jwt
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.tools import ToolResult
from starlette.applications import Starlette

from umbod.config import AppConfig, McpConfig
from umbod.mcp import public_app
from umbod.mcp.logging import McpAuditEvent, McpAuditRecorder
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, PrometheusMcpMetricsRecorder
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

READ_TOOL = "read_connector_configuration"
UPSERT_TOOL = "upsert_connector_configuration"
ADMINISTRATOR_GROUP = "umbod-administrators"


@dataclass(frozen=True)
class ConnectorReference:
    connector_kind: str
    connector_id: str


@dataclass(frozen=True)
class AdministratorPrincipal:
    email: str
    memberships: tuple[str, ...]


@dataclass
class AdminConnectorConfigurationJourney:
    app: Starlette
    token: str
    connector: ConnectorReference
    duplicate_capability_connector: ConnectorReference

    def transport(self) -> StreamableHttpTransport:
        asgi_transport = httpx2.ASGITransport(app=self.app)

        def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
            return httpx2.AsyncClient(transport=asgi_transport, **kwargs)

        return StreamableHttpTransport(
            "http://localhost/mcp",
            headers={"Authorization": f"Bearer {self.token}"},
            httpx_client_factory=create_http_client,
        )

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Client]:
        async with self.app.router.lifespan_context(self.app):
            async with Client(self.transport()) as client:
                yield client


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class CapturingPrometheusMetricsRecorder(PrometheusMcpMetricsRecorder):
    latest: "CapturingPrometheusMetricsRecorder"

    def __init__(self) -> None:
        self.invocations: list[CompletedToolInvocation] = []
        CapturingPrometheusMetricsRecorder.latest = self

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.invocations.append(invocation)


class AdminConnectorConfigurationDsl:
    def __init__(
        self,
        journey: AdminConnectorConfigurationJourney,
        connector: ConnectorReference | None = None,
    ) -> None:
        self._journey = journey
        self._connector = connector or journey.connector

    async def available_tools(self) -> set[str]:
        async with self._journey.client() as client:
            return {tool.name for tool in await client.list_tools()}

    async def read(self) -> ToolResult:
        async with self._journey.client() as client:
            return await client.call_tool(
                READ_TOOL,
                {
                    "connector_kind": self._connector.connector_kind,
                    "connector_id": self._connector.connector_id,
                },
                raise_on_error=False,
            )

    async def upsert_raw(self, desired_state: object) -> ToolResult:
        async with self._journey.client() as client:
            return await client.call_tool(
                UPSERT_TOOL,
                {
                    "connector_kind": self._connector.connector_kind,
                    "connector_id": self._connector.connector_id,
                    "desired_state": desired_state,
                },
                raise_on_error=False,
            )


def administrator() -> AdministratorPrincipal:
    return AdministratorPrincipal("admin@example.test", (ADMINISTRATOR_GROUP,))


def non_administrator() -> AdministratorPrincipal:
    return AdministratorPrincipal("engineer@example.test", ("engineering",))


def principal_without_membership_claim() -> AdministratorPrincipal:
    return AdministratorPrincipal("claimless@example.test", ())


def settings(
    database_path: Path,
    token: str,
    mcp_administrator_enabled: bool = True,
) -> AppConfig:
    return AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(database_path)},
        openapi_connectors={"json_import_max_bytes": 4096},
        mcp=McpConfig(
            auth_mode="single_test_user",
            test_bearer_token=token,
            permission_group_claim="groups",
            connector_tool_exposure_mode="codemode",
            downstream_discovery_enabled=False,
            stateless_http=True,
        ),
        endpoints={"mcp_base_url": "http://localhost"},
        feature_toggles={"mcp_administrator_enabled": mcp_administrator_enabled},
        admin_authentication={
            "mode": "simulation",
            "simulated_admin": True,
            "membership_claim": "groups",
            "required_membership": ADMINISTRATOR_GROUP,
        },
        connector_security={
            "configuration_secret": "acceptance-configuration-secret",
            "approval_state_key": "acceptance-approval-state-key-with-sufficient-entropy",
        },
    )


def token_for(principal: AdministratorPrincipal, include_memberships: bool = True) -> str:
    claims: dict[str, object] = {"sub": principal.email, "email": principal.email}
    if include_memberships:
        claims["groups"] = list(principal.memberships)
    return jwt.encode(claims, key="", algorithm="none")


async def create_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    principal: AdministratorPrincipal,
    include_memberships: bool = True,
    mcp_administrator_enabled: bool = True,
) -> AdminConnectorConfigurationJourney:
    availability_path = tmp_path / f"availability-{principal.email}.json"
    availability_path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    database_path = tmp_path / f"{principal.email}.sqlite3"
    token = token_for(principal, include_memberships)
    app_settings = settings(database_path, token, mcp_administrator_enabled)
    admin = TestClient(
        create_app(
            settings=APISettings.model_validate(app_settings.model_dump()),
            connector_registrations=[],
        )
    )
    response = admin.post(
        "/admin/connectors/openapi",
        json={"display_name": "Acceptance inventory", "capability_description": "Read inventory"},
    )
    assert response.status_code == 201
    connector = ConnectorReference("openapi", response.json()["connector_id"])
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Inventory", "version": "1"},
        "servers": [{"url": "https://inventory.example.test"}],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "summary": "List items",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    imported = admin.post(
        f"/admin/connectors/openapi/{connector.connector_id}/imports",
        json={"document": document, "approved_hosts": ["inventory.example.test"]},
    )
    assert imported.status_code == 201
    configured = admin.put(
        f"/admin/connectors/openapi/{connector.connector_id}/configuration",
        json={"authentication_type": "bearer", "bearer_token": "acceptance-secret-token"},
    )
    assert configured.status_code == 200
    activation = admin.put(
        f"/admin/connectors/openapi/{connector.connector_id}/tools/activation",
        json={
            "tools": [
                {
                    "tool_id": "listItems",
                    "activation_status": "enabled",
                    "invocation_mode": "ask",
                    "expected_policy_revision": 0,
                }
            ]
        },
    )
    assert activation.status_code == 200
    description = admin.put(
        f"/admin/connector-capability-descriptions/openapi/{connector.connector_id}",
        json={"action": "set", "description": "Custom inventory", "expected_revision": 0},
    )
    assert description.status_code == 200
    assert admin.post("/admin/mcp-permissions/groups/engineering").status_code == 200
    permissions = admin.put(
        "/admin/mcp-permissions/groups/engineering/permissions",
        json={
            "connectors": [
                {"connector_id": connector.connector_id, "permission_status": "enabled"}
            ],
            "capabilities": [
                {
                    "connector_id": connector.connector_id,
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "permission_status": "enabled",
                }
            ],
        },
    )
    assert permissions.status_code == 200
    duplicate_response = admin.post(
        "/admin/connectors/openapi",
        json={"display_name": "Second inventory", "capability_description": "Read inventory"},
    )
    assert duplicate_response.status_code == 201
    duplicate_connector = ConnectorReference("openapi", duplicate_response.json()["connector_id"])
    duplicate_import = admin.post(
        f"/admin/connectors/openapi/{duplicate_connector.connector_id}/imports",
        json={"document": document, "approved_hosts": ["inventory.example.test"]},
    )
    assert duplicate_import.status_code == 201
    duplicate_activation = admin.put(
        f"/admin/connectors/openapi/{duplicate_connector.connector_id}/tools/activation",
        json={
            "tools": [
                {
                    "tool_id": "listItems",
                    "activation_status": "enabled",
                    "invocation_mode": "direct",
                    "expected_policy_revision": 0,
                }
            ]
        },
    )
    assert duplicate_activation.status_code == 200
    config = await public_app.load_configured_public_app_config(app_settings)
    context = replace(await public_app.create_runtime_context(config), api_base_url=None)
    return AdminConnectorConfigurationJourney(
        await public_app.build_starlette_app(context),
        token,
        connector,
        duplicate_connector,
    )


@pytest.mark.asyncio
async def test_administrator_can_discover_and_read_connector_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    assert {READ_TOOL, UPSERT_TOOL} <= await configuration.available_tools()
    result = await configuration.read()
    assert result.is_error is False
    assert result.structured_content["connector"]["connector_kind"] == "openapi"
    assert result.structured_content["capabilities"] == [
        {
            "capability_kind": "tool",
            "capability_key": "listItems",
            "activation_status": "enabled",
            "invocation_policy": {"mode": "ask", "revision": 1},
        }
    ]
    assert result.structured_content["capability_description"] == {
        "state": "overridden",
        "revision": 1,
        "description": "Custom inventory",
    }
    assert result.structured_content["group_permissions"] == [
        {
            "group_id": "engineering",
            "connector_status": "enabled",
            "capabilities": [
                {
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "status": "enabled",
                }
            ],
        }
    ]
    assert "acceptance-secret-token" not in str(result.structured_content)
    assert "credential" not in str(result.structured_content).lower()


@pytest.mark.asyncio
async def test_administrator_read_records_one_internal_log_audit_and_metric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    monkeypatch.setattr(public_app, "create_default_mcp_tool_invocation_log_sink", lambda: invocation_sink)
    monkeypatch.setattr(public_app, "create_default_mcp_audit_recorder", lambda server_name: McpAuditRecorder(audit_sink, server_name))
    monkeypatch.setattr(public_app, "PrometheusMcpMetricsRecorder", CapturingPrometheusMetricsRecorder)
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )

    result = await configuration.read()

    assert result.is_error is False
    records = invocation_sink.invocation_records()
    assert len(records) == 1
    assert records[0].attributes["mcp.tool.name"] == READ_TOOL
    assert "mcp.connector.id" not in records[0].attributes
    assert "mcp.connector.name" not in records[0].attributes
    assert "mcp.operation.name" not in records[0].attributes
    invocation_events = [event for event in audit_sink.events if event.activity_type.value == "tool_invocation"]
    assert len(invocation_events) == 1
    assert invocation_events[0].target.tool_name == READ_TOOL
    assert invocation_events[0].target.attributes == {}
    invocations = CapturingPrometheusMetricsRecorder.latest.invocations
    assert invocations == [
        CompletedToolInvocation(
            connector_name="internal",
            tool_name=READ_TOOL,
            outcome=InvocationOutcome.SUCCESS,
            duration_seconds=invocations[0].duration_seconds,
        )
    ]


@pytest.mark.asyncio
async def test_empty_desired_state_is_idempotent_no_op_with_complete_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    first_upsert = await configuration.upsert_raw({"operations": []})
    second_upsert = await configuration.upsert_raw({"operations": []})
    after = await configuration.read()

    assert before.is_error is False
    assert first_upsert.is_error is False
    assert second_upsert.is_error is False
    assert after.is_error is False
    assert first_upsert.structured_content == before.structured_content
    assert second_upsert.structured_content == before.structured_content
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_partial_activation_upsert_preserves_omitted_state_and_connector_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journey = await create_journey(tmp_path, monkeypatch, administrator())
    configuration = AdminConnectorConfigurationDsl(journey)
    duplicate_configuration = AdminConnectorConfigurationDsl(
        journey, journey.duplicate_capability_connector
    )
    before = await configuration.read()
    result = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_activation",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "activation_status": "disabled",
                }
            ]
        }
    )
    duplicate = await duplicate_configuration.read()

    assert before.is_error is False
    assert result.is_error is False
    assert result.structured_content["capabilities"] == [
        {
            **before.structured_content["capabilities"][0],
            "activation_status": "disabled",
        }
    ]
    assert result.structured_content["capability_description"] == before.structured_content[
        "capability_description"
    ]
    assert result.structured_content["group_permissions"] == before.structured_content[
        "group_permissions"
    ]
    assert duplicate.is_error is False
    assert duplicate.structured_content["capabilities"][0]["capability_key"] == "listItems"
    assert duplicate.structured_content["capabilities"][0]["activation_status"] == "enabled"


@pytest.mark.asyncio
async def test_invocation_mode_upsert_preserves_omitted_state_and_idempotent_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    changed = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_invocation_policy",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "mode": "direct",
                    "expected_revision": 1,
                }
            ]
        }
    )
    unchanged = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_invocation_policy",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "mode": "direct",
                    "expected_revision": 2,
                }
            ]
        }
    )

    assert before.is_error is False
    assert changed.is_error is False
    assert changed.structured_content["capabilities"] == [
        {
            **before.structured_content["capabilities"][0],
            "invocation_policy": {"mode": "direct", "revision": 2},
        }
    ]
    assert changed.structured_content["capability_description"] == before.structured_content[
        "capability_description"
    ]
    assert changed.structured_content["group_permissions"] == before.structured_content[
        "group_permissions"
    ]
    assert unchanged.is_error is False
    assert unchanged.structured_content == changed.structured_content


@pytest.mark.asyncio
async def test_description_override_upsert_preserves_omitted_state_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    changed = await configuration.upsert_raw(
        {
            "operations": [{
                "operation": "set_capability_description",
                "description": "Updated inventory description",
                "expected_revision": 1,
            }]
        }
    )
    unchanged = await configuration.upsert_raw(
        {
            "operations": [{
                "operation": "set_capability_description",
                "description": "Updated inventory description",
                "expected_revision": 2,
            }]
        }
    )

    assert changed.is_error is False
    assert changed.structured_content["capability_description"] == {
        "state": "overridden",
        "revision": 2,
        "description": "Updated inventory description",
    }
    assert changed.structured_content["capabilities"] == before.structured_content["capabilities"]
    assert changed.structured_content["group_permissions"] == before.structured_content[
        "group_permissions"
    ]
    assert unchanged.is_error is False
    assert unchanged.structured_content == changed.structured_content


@pytest.mark.asyncio
async def test_restore_system_description_returns_complete_state_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    restored = await configuration.upsert_raw(
        {
            "operations": [{
                "operation": "use_system_capability_description",
                "expected_revision": 1,
            }]
        }
    )
    unchanged = await configuration.upsert_raw(
        {
            "operations": [{
                "operation": "use_system_capability_description",
                "expected_revision": 2,
            }]
        }
    )

    assert restored.is_error is False
    assert restored.structured_content["capability_description"] == {
        "state": "system",
        "revision": 2,
    }
    assert restored.structured_content["capabilities"] == before.structured_content["capabilities"]
    assert restored.structured_content["group_permissions"] == before.structured_content[
        "group_permissions"
    ]
    assert unchanged.is_error is False
    assert unchanged.structured_content == restored.structured_content


@pytest.mark.asyncio
async def test_partial_group_permission_upsert_supports_connector_and_capability_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    disabled = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "update_group_permissions",
                    "group_id": "engineering",
                    "connector_status": "disabled",
                    "capabilities": [
                        {
                            "capability_kind": "tool",
                            "capability_key": "listItems",
                            "status": "disabled",
                        }
                    ],
                }
            ]
        }
    )
    capability_granted = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "update_group_permissions",
                    "group_id": "engineering",
                    "capabilities": [
                        {
                            "capability_kind": "tool",
                            "capability_key": "listItems",
                            "status": "enabled",
                        }
                    ],
                }
            ]
        }
    )
    connector_granted = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "update_group_permissions",
                    "group_id": "engineering",
                    "connector_status": "enabled",
                }
            ]
        }
    )
    after = await configuration.read()

    assert before.is_error is False
    assert disabled.is_error is False
    assert disabled.structured_content["group_permissions"] == [
        {
            "group_id": "engineering",
            "connector_status": "disabled",
            "capabilities": [
                {
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "status": "disabled",
                }
            ],
        }
    ]
    assert disabled.structured_content["capabilities"] == before.structured_content["capabilities"]
    assert disabled.structured_content["capability_description"] == before.structured_content[
        "capability_description"
    ]
    assert capability_granted.structured_content["group_permissions"][0] == {
        "group_id": "engineering",
        "connector_status": "disabled",
        "capabilities": [
            {
                "capability_kind": "tool",
                "capability_key": "listItems",
                "status": "enabled",
            }
        ],
    }
    assert connector_granted.structured_content == before.structured_content
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_unknown_permission_target_is_rejected_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    result = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "update_group_permissions",
                    "group_id": "engineering",
                    "connector_status": "disabled",
                    "capabilities": [
                        {
                            "capability_kind": "tool",
                            "capability_key": "missingTool",
                            "status": "enabled",
                        }
                    ],
                }
            ]
        }
    )
    after = await configuration.read()

    assert result.is_error is True
    assert "missingTool" in str(result)
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_stale_description_revision_reports_conflict_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    result = await configuration.upsert_raw(
        {
            "operations": [{
                "operation": "set_capability_description",
                "description": "Rejected stale description",
                "expected_revision": 0,
            }]
        }
    )
    after = await configuration.read()

    assert result.is_error is True
    assert "capability_description" in str(result)
    assert "expected revision 0" in str(result)
    assert "current revision 1" in str(result)
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_stale_invocation_policy_revision_reports_conflict_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    result = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_invocation_policy",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "mode": "direct",
                    "expected_revision": 0,
                }
            ]
        }
    )
    after = await configuration.read()

    assert result.is_error is True
    assert "tool/listItems/invocation_policy" in str(result)
    assert "expected revision 0" in str(result)
    assert "current revision 1" in str(result)
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_unknown_activation_targets_are_rejected_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journey = await create_journey(tmp_path, monkeypatch, administrator())
    configuration = AdminConnectorConfigurationDsl(journey)
    before = await configuration.read()
    unknown_capability = await configuration.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_activation",
                    "capability_kind": "tool",
                    "capability_key": "missingTool",
                    "activation_status": "disabled",
                },
                {
                    "operation": "set_capability_activation",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "activation_status": "disabled",
                },
            ]
        }
    )
    after = await configuration.read()
    unknown_connector = AdminConnectorConfigurationDsl(
        journey, ConnectorReference("openapi", "unknown-connector")
    )
    unknown_connector_result = await unknown_connector.upsert_raw(
        {
            "operations": [
                {
                    "operation": "set_capability_activation",
                    "capability_kind": "tool",
                    "capability_key": "listItems",
                    "activation_status": "disabled",
                }
            ]
        }
    )

    assert unknown_capability.is_error is True
    assert "missingTool" in str(unknown_capability)
    assert after.structured_content == before.structured_content
    assert unknown_connector_result.is_error is True
    assert "unknown-connector" in str(unknown_connector_result)


@pytest.mark.asyncio
async def test_combined_desired_state_applies_every_dimension_and_repeated_upsert_is_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    desired_state = {
        "operations": [
            {"operation": "set_capability_activation", "capability_kind": "tool", "capability_key": "listItems", "activation_status": "disabled"},
            {"operation": "set_capability_invocation_policy", "capability_kind": "tool", "capability_key": "listItems", "mode": "direct", "expected_revision": 1},
            {"operation": "set_capability_description", "description": "Combined inventory description", "expected_revision": 1},
            {
                "operation": "update_group_permissions",
                "group_id": "engineering",
                "connector_status": "disabled",
                "capabilities": [{"capability_kind": "tool", "capability_key": "listItems", "status": "disabled"}],
            },
        ],
    }
    changed = await configuration.upsert_raw(desired_state)
    repeated_state = {
        "operations": [
            operation | {"expected_revision": 2}
            if operation["operation"] in {"set_capability_invocation_policy", "set_capability_description"}
            else operation
            for operation in desired_state["operations"]
        ],
    }
    unchanged = await configuration.upsert_raw(repeated_state)
    read_back = await configuration.read()

    expected = {
        "connector": changed.structured_content["connector"],
        "capabilities": [
            {
                "capability_kind": "tool",
                "capability_key": "listItems",
                "activation_status": "disabled",
                "invocation_policy": {"mode": "direct", "revision": 2},
            }
        ],
        "capability_description": {
            "state": "overridden",
            "description": "Combined inventory description",
            "revision": 2,
        },
        "group_permissions": [
            {
                "group_id": "engineering",
                "connector_status": "disabled",
                "capabilities": [
                    {
                        "capability_kind": "tool",
                        "capability_key": "listItems",
                        "status": "disabled",
                    }
                ],
            }
        ],
    }
    assert changed.is_error is False
    assert changed.structured_content == expected
    assert unchanged.is_error is False
    assert unchanged.structured_content == expected
    assert read_back.is_error is False
    assert read_back.structured_content == expected


@pytest.mark.asyncio
async def test_combined_stale_request_rolls_back_every_configuration_dimension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    before = await configuration.read()
    rejected = await configuration.upsert_raw(
        {
            "operations": [
                {"operation": "set_capability_activation", "capability_kind": "tool", "capability_key": "listItems", "activation_status": "disabled"},
                {"operation": "set_capability_invocation_policy", "capability_kind": "tool", "capability_key": "listItems", "mode": "direct", "expected_revision": 0},
                {"operation": "set_capability_description", "description": "Must not persist", "expected_revision": 1},
                {
                    "operation": "update_group_permissions",
                    "group_id": "engineering",
                    "connector_status": "disabled",
                    "capabilities": [{"capability_kind": "tool", "capability_key": "listItems", "status": "disabled"}],
                },
            ],
        }
    )
    after = await configuration.read()

    assert rejected.is_error is True
    assert "tool/listItems/invocation_policy" in str(rejected)
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_malformed_desired_state_is_rejected_at_mcp_tool_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(tmp_path, monkeypatch, administrator())
    )
    result = await configuration.upsert_raw(
        {"operations": "this must be an array of structured declarations"}
    )
    assert result.is_error is True
    assert "validation" in str(result).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("principal", "include_memberships"),
    [
        (non_administrator(), True),
        (principal_without_membership_claim(), False),
    ],
    ids=["non-administrator", "missing-membership-claim"],
)
async def test_unauthorized_caller_cannot_discover_administration_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    principal: AdministratorPrincipal,
    include_memberships: bool,
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(
            tmp_path,
            monkeypatch,
            principal,
            include_memberships,
        )
    )
    assert {READ_TOOL, UPSERT_TOOL}.isdisjoint(await configuration.available_tools())


@pytest.mark.asyncio
async def test_disabled_feature_hides_administration_tools_from_administrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(
            tmp_path,
            monkeypatch,
            administrator(),
            mcp_administrator_enabled=False,
        )
    )
    assert {READ_TOOL, UPSERT_TOOL}.isdisjoint(await configuration.available_tools())
