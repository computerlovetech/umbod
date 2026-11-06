from umbod.logging import create_application_failure_signal
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx2
import jwt
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.tools import ToolResult
from starlette.applications import Starlette

from umbod.config import AppConfig, McpConfig
from tests.mcp_fixtures import empty_connector_plugins
from umbod.mcp import public_app
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.telemetry import McpTelemetryDependencies
from tests.mcp_telemetry_fixtures import RecordingApplicationMetricsRecorder, RecordingAuditSink, RecordingMetricsServerFactory
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, InvocationScope
from umbod.infrastructure import AppPersistenceRuntime
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
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
        async with Client(self.transport()) as client:
            yield client


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
    token: str,
    mcp_administrator_enabled: bool = True,
) -> AppConfig:
    return AppConfig(
        connector_store={"type": "inmemory"},
        rest={"metrics_enabled": False},
        openapi_connectors={"json_import_max_bytes": 4096},
        mcp=McpConfig(
            metrics_enabled=False,
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


def inventory_document() -> dict[str, Any]:
    return {
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


async def prepare_connector(admin: httpx2.AsyncClient) -> ConnectorReference:
    response = await admin.post(
        "/api/admin/connectors/openapi",
        json={"display_name": "Acceptance inventory", "capability_description": "Read inventory"},
    )
    assert response.status_code == 201
    connector = ConnectorReference("openapi", response.json()["connector_id"])
    document = inventory_document()
    imported = await admin.post(
        f"/api/admin/connectors/openapi/{connector.connector_id}/imports",
        json={"document": document, "approved_hosts": ["inventory.example.test"]},
    )
    assert imported.status_code == 201
    configured = await admin.put(
        f"/api/admin/connectors/openapi/{connector.connector_id}/configuration",
        json={"authentication_type": "bearer", "bearer_token": "acceptance-secret-token"},
    )
    assert configured.status_code == 200
    activation = await admin.put(
        f"/api/admin/connectors/openapi/{connector.connector_id}/tools/activation",
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
    description = await admin.put(
        f"/api/admin/connector-capability-descriptions/openapi/{connector.connector_id}",
        json={"action": "set", "description": "Custom inventory", "expected_revision": 0},
    )
    assert description.status_code == 200
    assert (await admin.post("/api/admin/mcp-permissions/groups/engineering")).status_code == 200
    permissions = await admin.put(
        "/api/admin/mcp-permissions/groups/engineering/permissions",
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
    return connector


async def prepare_duplicate_connector(admin: httpx2.AsyncClient) -> ConnectorReference:
    document = inventory_document()
    duplicate_response = await admin.post(
        "/api/admin/connectors/openapi",
        json={"display_name": "Second inventory", "capability_description": "Read inventory"},
    )
    assert duplicate_response.status_code == 201
    duplicate_connector = ConnectorReference("openapi", duplicate_response.json()["connector_id"])
    duplicate_import = await admin.post(
        f"/api/admin/connectors/openapi/{duplicate_connector.connector_id}/imports",
        json={"document": document, "approved_hosts": ["inventory.example.test"]},
    )
    assert duplicate_import.status_code == 201
    duplicate_activation = await admin.put(
        f"/api/admin/connectors/openapi/{duplicate_connector.connector_id}/tools/activation",
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
    return duplicate_connector


@dataclass(frozen=True)
class ConnectorIsolationArrangement:
    journey: AdminConnectorConfigurationJourney
    duplicate_capability_connector: ConnectorReference


class AdminConnectorConfigurationJourneyFactory:
    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stack: AsyncExitStack
    ) -> None:
        self._tmp_path = tmp_path
        self._monkeypatch = monkeypatch
        self._stack = stack

    def prepare_settings(
        self,
        principal: AdministratorPrincipal,
        include_memberships: bool,
        mcp_administrator_enabled: bool,
    ) -> tuple[AppConfig, str]:
        tmp_path = self._tmp_path
        monkeypatch = self._monkeypatch
        availability_path = tmp_path / f"availability-{principal.email}.json"
        availability_path.write_text('{"connectors": []}', encoding="utf-8")
        monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
        token = token_for(principal, include_memberships)
        app_settings = settings(token, mcp_administrator_enabled)
        return app_settings, token

    async def prepare_config(
        self, app_settings: AppConfig, *telemetry_bundles: McpTelemetryDependencies,
    ) -> PublicAppConfig:
        self._monkeypatch.setattr(public_app, "load_connector_plugins", empty_connector_plugins)
        config = await public_app.load_configured_public_app_config(app_settings)
        self._stack.push_async_callback(config.persistence_runtime.shutdown)
        application_runtime = AppPersistenceRuntime(
            database=config.persistence_runtime.database, readiness=config.persistence_runtime.readiness,
        )
        config = replace(
            config, persistence_runtime=application_runtime,
            configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), api_base_url=None,
        )
        if telemetry_bundles:
            config = replace(config, telemetry=telemetry_bundles[0])
        return config

    @asynccontextmanager
    async def admin_client(self, config: PublicAppConfig) -> AsyncIterator[httpx2.AsyncClient]:
        runtime = AppPersistenceRuntime(
            database=config.persistence_runtime.database, readiness=config.persistence_runtime.readiness,
        )
        factories = ConnectorApiDependencyFactories.from_settings(
            APISettings.model_validate(config.settings.model_dump()), runtime, [],
        )
        app = create_app_with_dependency_factories(factories)
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://testserver",
        ) as admin:
            yield admin

    async def __call__(
        self,
        principal: AdministratorPrincipal,
        *telemetry_bundles: McpTelemetryDependencies,
        include_memberships: bool = True,
        mcp_administrator_enabled: bool = True,
    ) -> AdminConnectorConfigurationJourney:
        if len(telemetry_bundles) > 1:
            raise TypeError("At most one telemetry bundle may be supplied")
        app_settings, token = self.prepare_settings(
            principal, include_memberships, mcp_administrator_enabled
        )
        config = await self.prepare_config(app_settings, *telemetry_bundles)
        async with self.admin_client(config) as admin:
            connector = await prepare_connector(admin)
        return await self.start(config, token, connector)

    async def isolation(self) -> ConnectorIsolationArrangement:
        app_settings, token = self.prepare_settings(administrator(), True, True)
        config = await self.prepare_config(app_settings)
        async with self.admin_client(config) as admin:
            connector = await prepare_connector(admin)
            duplicate_connector = await prepare_duplicate_connector(admin)
        journey = await self.start(config, token, connector)
        return ConnectorIsolationArrangement(journey, duplicate_connector)

    async def start(
        self,
        config: PublicAppConfig,
        token: str,
        connector: ConnectorReference,
    ) -> AdminConnectorConfigurationJourney:
        try:
            context = await public_app.create_runtime_context(
                config,
                downstream_client_factory=await create_configured_downstream_client_factory(
                    config.settings, config.persistence_runtime.database,
                ),
                openapi_adapters=create_configured_openapi_runtime_adapters(config.settings),
            )
            app = await public_app.build_starlette_app(context)
        except BaseException:
            await config.persistence_runtime.shutdown()
            raise
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        stop = asyncio.Event()
        task = asyncio.create_task(own_application_lifespan(app, ready, stop))
        self._stack.push_async_callback(close_application_lifespan, task, stop)
        try:
            await asyncio.shield(ready)
        except BaseException:
            stop.set()
            await task
            if ready.done() and not ready.cancelled():
                ready.exception()
            raise
        return AdminConnectorConfigurationJourney(app, token, connector)


async def own_application_lifespan(
    app: Starlette, ready: asyncio.Future[None], stop: asyncio.Event
) -> None:
    try:
        async with app.router.lifespan_context(app):
            ready.set_result(None)
            await stop.wait()
    except BaseException as error:
        if ready.done():
            raise
        ready.set_exception(error)


async def close_application_lifespan(
    task: asyncio.Task[None], stop: asyncio.Event
) -> None:
    stop.set()
    await task


@pytest_asyncio.fixture
async def create_journey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AdminConnectorConfigurationJourneyFactory]:
    async with AsyncExitStack() as stack:
        yield AdminConnectorConfigurationJourneyFactory(tmp_path, monkeypatch, stack)


@pytest.mark.asyncio
async def test_administrator_can_discover_and_read_connector_configuration(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    metrics = RecordingApplicationMetricsRecorder()
    listeners = RecordingMetricsServerFactory()
    telemetry = McpTelemetryDependencies(create_application_failure_signal(), invocation_sink, McpAuditRecorder(audit_sink, "test", application_failures=create_application_failure_signal()), metrics, listeners)
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator(), telemetry)
    )

    result = await configuration.read()

    assert result.is_error is False
    assert listeners.servers == []
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
    invocations = metrics.invocations
    assert invocations == [
        CompletedToolInvocation(
            scope=InvocationScope.REQUEST,
            connector_name="internal",
            tool_name=READ_TOOL,
            outcome=InvocationOutcome.SUCCESS,
            duration_seconds=max(records[0].attributes["mcp.invocation.duration_ms"] / 1000, 1e-12),
        )
    ]


@pytest.mark.asyncio
async def test_empty_desired_state_is_idempotent_no_op_with_complete_read_back(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    arrangement = await create_journey.isolation()
    configuration = AdminConnectorConfigurationDsl(arrangement.journey)
    duplicate_configuration = AdminConnectorConfigurationDsl(
        arrangement.journey, arrangement.duplicate_capability_connector
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    assert result.meta["computerlove.tech/umbod"]["guidance"]["error"]["code"] == "capability_not_found"
    assert "missingTool" not in str(result)
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_stale_description_revision_reports_conflict_without_write(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    assert result.meta["computerlove.tech/umbod"]["guidance"]["error"]["code"] == "revision_conflict"
    assert result.meta["computerlove.tech/umbod"]["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_unknown_activation_targets_are_rejected_before_any_write(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    journey = await create_journey(administrator())
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
    assert unknown_capability.meta["computerlove.tech/umbod"]["guidance"]["error"]["code"] == "capability_not_found"
    assert "missingTool" not in str(unknown_capability)
    assert after.structured_content == before.structured_content
    assert unknown_connector_result.is_error is True
    assert unknown_connector_result.meta["computerlove.tech/umbod"]["guidance"]["error"]["code"] == "connector_not_found"
    assert "unknown-connector" not in str(unknown_connector_result)


@pytest.mark.asyncio
async def test_combined_desired_state_applies_every_dimension_and_repeated_upsert_is_no_op(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
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
    assert rejected.meta["computerlove.tech/umbod"]["guidance"]["error"]["code"] == "revision_conflict"
    assert rejected.meta["computerlove.tech/umbod"]["guidance"]["operation_state"] == "unknown"
    assert rejected.meta["computerlove.tech/umbod"]["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    instructions = rejected.meta["computerlove.tech/umbod"]["guidance"]["recovery"]["instructions"]
    assert any("read_connector_configuration" in instruction for instruction in instructions)
    for instruction in instructions:
        assert instruction in rejected.content[1].text
    assert "unknown" in rejected.content[1].text
    assert "inspect_before_retry" in rejected.content[1].text
    assert after.structured_content == before.structured_content


@pytest.mark.asyncio
async def test_malformed_desired_state_is_rejected_at_mcp_tool_boundary(
    create_journey: AdminConnectorConfigurationJourneyFactory
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(administrator())
    )
    result = await configuration.upsert_raw(
        {"operations": "this must be an array of structured declarations"}
    )
    assert result.is_error is True
    details = result.meta["computerlove.tech/umbod"]
    assert details["guidance"]["error"]["code"] == "invalid_arguments"
    assert details["guidance"]["operation_state"] == "not_started"
    assert details["guidance"]["recovery"]["retry"] == "after_correction"
    assert details["guidance"]["error"]["issues"][0]["field"] == "desired_state.operations"


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
    create_journey: AdminConnectorConfigurationJourneyFactory,
    principal: AdministratorPrincipal,
    include_memberships: bool,
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(
            principal,
            include_memberships=include_memberships,
        )
    )
    assert {READ_TOOL, UPSERT_TOOL}.isdisjoint(await configuration.available_tools())


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [READ_TOOL, UPSERT_TOOL])
async def test_builtin_administration_success_metadata_preserves_declared_schemas(
    create_journey: AdminConnectorConfigurationJourneyFactory, tool: str,
) -> None:
    journey = await create_journey(administrator())
    arguments: dict[str, Any] = {
        "connector_kind": journey.connector.connector_kind,
        "connector_id": journey.connector.connector_id,
    }
    if tool == UPSERT_TOOL:
        arguments["desired_state"] = {"operations": []}
    async with journey.client() as client:
        before = next(item for item in await client.list_tools() if item.name == tool)
        result = await client.call_tool(tool, arguments)
        after = next(item for item in await client.list_tools() if item.name == tool)
    metadata = result.meta["computerlove.tech/umbod"]
    assert metadata["schema_version"] == 1
    assert metadata["guidance"]["outcome"] == "success"
    assert metadata["guidance"]["operation_state"] == "completed"
    assert metadata["guidance"]["recovery"]["retry"] == "not_needed"
    assert metadata["guidance"]["error"] is None
    assert metadata["guidance"]["recovery"]["instructions"] == []
    assert metadata["guidance"]["notices"] == []
    assert metadata["guidance"]["extensions"] == {}
    assert metadata["extensions"] == {}
    assert result.structured_content["connector"]["connector_id"] == journey.connector.connector_id
    assert before.input_schema == after.input_schema
    assert before.output_schema == after.output_schema


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [READ_TOOL, UPSERT_TOOL])
@pytest.mark.parametrize("connector_id,connector_kind,field", [
    ("", "native", "connector_id"),
    ("SECRET_ID", "SECRET_KIND", "connector_kind"),
])
async def test_builtin_administration_invalid_arguments_have_safe_field_diagnostics(
    create_journey: AdminConnectorConfigurationJourneyFactory, tool: str,
    connector_id: str, connector_kind: str, field: str,
) -> None:
    journey = await create_journey(administrator())
    arguments: dict[str, Any] = {"connector_kind": connector_kind, "connector_id": connector_id}
    if tool == UPSERT_TOOL:
        arguments["desired_state"] = {"operations": []}
    async with journey.client() as client:
        result = await client.call_tool(tool, arguments, raise_on_error=False)
    metadata = result.meta["computerlove.tech/umbod"]
    assert result.is_error
    assert metadata["guidance"]["outcome"] == "failure"
    assert metadata["guidance"]["operation_state"] == "not_started"
    assert metadata["guidance"]["recovery"]["retry"] == "after_correction"
    assert metadata["guidance"]["error"]["code"] == "invalid_arguments"
    assert field in {issue["field"] for issue in metadata["guidance"]["error"]["issues"]}
    assert "SECRET" not in repr(result)


@pytest.mark.asyncio
async def test_disabled_feature_hides_administration_tools_from_administrator(
    create_journey: AdminConnectorConfigurationJourneyFactory,
) -> None:
    configuration = AdminConnectorConfigurationDsl(
        await create_journey(
            administrator(),
            mcp_administrator_enabled=False,
        )
    )
    assert {READ_TOOL, UPSERT_TOOL}.isdisjoint(await configuration.available_tools())
