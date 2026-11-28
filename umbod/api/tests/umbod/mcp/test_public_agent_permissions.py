from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx2
import pytest
from cryptography.fernet import Fernet
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from pydantic import SecretStr
from starlette.applications import Starlette

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.umbod.mcp.connectors.native.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolMapping,
    InMemoryConnectorPublishingStore,
)
from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.administrator.operations import AdministratorAccess
from umbod.core.agent_tokens import (
    AgentCredentialService,
    CreateAgent,
    create_agent_credential_service,
    create_agent_credential_verifier,
)
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.groups import GroupInstance
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.core.invocation.policy import ConnectorInvocationPolicyKey, ConnectorInvocationPolicyUpdate
from umbod.core.permissions.domain import ConnectorCapabilityRef, GroupPermissionSet, SaveGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_instance_permission_reader, create_group_permission_store
from umbod.core.permissions.ports import GroupInstancePermissionReader, GroupPermissionStore
from umbod.core.persistence import Database
from umbod.core.system_settings import UpdatePortableConnectorSettings, create_system_settings_service
from umbod.mcp.auth.agent_tokens import create_public_agent_auth
from umbod.mcp.auth.factory import MCPAuthProviderFactory
from umbod.mcp.auth.transport import AuthenticatedMcpTransport
from umbod.mcp.http_transport import MAX_MCP_REQUEST_BODY_BYTES, create_mcp_http_app
from umbod.mcp.public_app import build_mcp_with_openapi_adapters
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.mcp.settings import MCPAppSettings, MCPSettings, OIDCOAuthStorageSettings, OIDCSettings
from umbod.mcp.telemetry.composition import create_configured_mcp_telemetry

_GROUP = "agent-operators"
_ALLOWED = ConnectorCapabilityRef("slack", "tool", "read")
_DENIED = ConnectorCapabilityRef("slack", "tool", "write")
_ADMIN = AdministratorPrincipal(memberships=("administrators",))
ExposureMode = Literal["flat", "gateway", "codemode"]


@dataclass(frozen=True)
class _AgentSession:
    client: Client
    http: httpx2.AsyncClient
    permissions: GroupPermissionStore
    credentials: AgentCredentialService
    agent_id: str
    token: SecretStr
    invocations: list[str]
    database: Database


async def _set_permissions(permissions: GroupPermissionStore, *refs: ConnectorCapabilityRef) -> None:
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(_GROUP, ("slack",), refs))


async def _connector_runtime(invocations: list[str]) -> ConnectorRuntime:
    def read() -> dict[str, bool]:
        invocations.append("read")
        return {"ok": True}

    def write() -> dict[str, bool]:
        invocations.append("write")
        return {"ok": True}

    configuration = InMemoryConnectorCurrentConfigurationStore()
    await configuration.save_current_configuration("slack", SlackAdminConfiguration(
        workspace_name="Workspace", bot_token=SecretStr("test"), default_channel_id="C-AGENTS",
    ))
    publishing = InMemoryConnectorPublishingStore()
    await publishing.publish_connector("slack")
    return ConnectorRuntime(
        connector_registrations=[{"id": "slack", "display_name": "Slack", "capability_description": "Channel operations", "configuration_schema": SlackAdminConfiguration}],
        connector_configuration_store=configuration,
        connector_publishing_store=publishing,
        connector_tool_mappings=[
            ConnectorToolMapping("slack", "read", "Channel read operation", read),
            ConnectorToolMapping("slack", "write", "Channel write operation", write),
        ],
    )


def _transport(app: Starlette, token: SecretStr) -> StreamableHttpTransport:
    def create_client(**options: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **options)

    return StreamableHttpTransport(
        "http://localhost/mcp", headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        httpx_client_factory=create_client,
    )


@asynccontextmanager
async def _agent_session(path: Path, mode: ExposureMode, *, stateless: bool) -> AsyncIterator[_AgentSession]:
    runtime = await prepared_inmemory_runtime()
    try:
        permissions = await create_group_permission_store(runtime.database)
        await _set_permissions(permissions, _ALLOWED)
        credentials = create_agent_credential_service(runtime.database, AdministratorAccess("administrators"))
        issued = await credentials.create(_ADMIN, CreateAgent(
            display_name="Automation", group_id=_GROUP, expires_at=datetime.now(UTC) + timedelta(hours=1),
        ))
        settings = MCPAppSettings(
            mcp=MCPSettings(auth_mode="oidc", connector_tool_exposure_mode=mode),
            oidc=OIDCSettings(provider="google", client_id="oauth-client", client_secret="oauth-secret", required_scopes=["read"]),
            oauth_storage=OIDCOAuthStorageSettings(directory=str(path / "oauth"), encryption_key=Fernet.generate_key().decode()),
        )
        oauth = MCPAuthProviderFactory().create(settings)
        assert oauth is not None
        composite = create_public_agent_auth(oauth, create_agent_credential_verifier(runtime.database))
        invocations: list[str] = []
        server = await build_mcp_with_openapi_adapters(
            settings, AuthenticatedMcpTransport(composite), await _connector_runtime(invocations), (),
            create_configured_openapi_runtime_adapters(settings), runtime,
            telemetry=create_configured_mcp_telemetry(settings),
            downstream_client_factory=await create_configured_downstream_client_factory(settings, runtime.database),
        )

        @server.tool(meta={"connector_id": "slack", "operation_name": "read"})
        def unrelated_extension() -> str:
            invocations.append("extension")
            return "not allowed"

        app = create_mcp_http_app(server, path="/mcp", stateless_http=stateless, max_request_body_bytes=MAX_MCP_REQUEST_BODY_BYTES)
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://localhost") as http,
            Client(_transport(app, issued.token)) as client,
        ):
            yield _AgentSession(client, http, permissions, credentials, issued.metadata.agent_id, issued.token, invocations, runtime.database)
    finally:
        await runtime.shutdown()


async def _discover(client: Client, mode: ExposureMode) -> set[str]:
    if mode == "flat":
        return {tool.name for tool in await client.list_tools()}
    result = await client.call_tool("search_tools", {"query": "channel"})
    assert result.structured_content is not None
    return {match["tool_name"] for match in result.structured_content["matches"]}


async def _invoke(client: Client, mode: ExposureMode, name: str) -> bool:
    if mode == "flat":
        result = await client.call_tool(name, {})
    elif mode == "gateway":
        result = await client.call_tool("execute_tool", {"tool_name": name, "arguments": {}})
    else:
        result = await client.call_tool("execute_code", {"code": f"{name}()"}, raise_on_error=False)
        return not result.is_error and (result.structured_content or {}).get("outcome") == "success"
    return not result.is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode"])
async def test_agent_http_discovers_and_invokes_only_current_exact_native_grants(tmp_path: Path, mode: ExposureMode) -> None:
    async with _agent_session(tmp_path, mode, stateless=True) as session:
        assert await _discover(session.client, mode) == {"slack_read"}
        assert await _invoke(session.client, mode, "slack_read")
        if mode == "codemode":
            assert not await _invoke(session.client, mode, "slack_write")
        else:
            with pytest.raises(ToolError):
                await _invoke(session.client, mode, "slack_write")
        with pytest.raises(ToolError):
            await session.client.call_tool("unrelated_extension", {})
        await _set_permissions(session.permissions)
        assert await _discover(session.client, mode) == set()
        if mode == "codemode":
            assert not await _invoke(session.client, mode, "slack_read")
        else:
            with pytest.raises(ToolError):
                await _invoke(session.client, mode, "slack_read")
        assert session.invocations == ["read"]


@pytest.mark.asyncio
async def test_agent_cannot_run_an_ask_tool_without_human_approval(tmp_path: Path) -> None:
    async with _agent_session(tmp_path, "flat", stateless=True) as session:
        policy = DatabaseConnectorInvocationPolicyStore(session.database)
        await policy.compare_and_set_batch((ConnectorInvocationPolicyUpdate(
            key=ConnectorInvocationPolicyKey("native", "slack", "read"), mode="ask", expected_revision=0,
        ),))
        with pytest.raises(ToolError):
            await session.client.call_tool("slack_read", {})
        assert session.invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["discovery", "invocation"])
async def test_replaced_group_after_bearer_verification_cannot_authorize_stale_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: Literal["discovery", "invocation"],
) -> None:
    replaced = False

    def replace_group_on_permission_read(database: Database) -> GroupInstancePermissionReader:
        reader = create_group_instance_permission_reader(database)

        class ReplacingGroupReader:
            async def read_for_group_instance(self, group: GroupInstance) -> GroupPermissionSet:
                nonlocal replaced
                permissions = await create_group_permission_store(database)
                await permissions.save_group_permissions(SaveGroupPermissionsRequest(group.group_id, (), ()))
                await create_group_management(database).delete_group(group.group_id)
                await _set_permissions(permissions, _DENIED)
                replaced = True
                return await reader.read_for_group_instance(group)

        return ReplacingGroupReader()

    monkeypatch.setattr("umbod.mcp.public_app.create_group_instance_permission_reader", replace_group_on_permission_read)
    async with _agent_session(tmp_path, "gateway", stateless=True) as session:
        if operation == "discovery":
            assert await session.client.list_tools() == []
        else:
            with pytest.raises(ToolError):
                await _invoke(session.client, "gateway", "slack_write")
        assert replaced
        assert session.invocations == []


@pytest.mark.asyncio
async def test_revoked_agent_is_rejected_on_the_next_http_request_with_same_session(tmp_path: Path) -> None:
    async with _agent_session(tmp_path, "flat", stateless=False) as session:
        headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        authorized = {"Authorization": f"Bearer {session.token.get_secret_value()}"}
        initialized = await session.http.post("/mcp", headers={**headers, **authorized}, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}},
        })
        assert initialized.status_code == 200
        headers["Mcp-Session-Id"] = initialized.headers["Mcp-Session-Id"]
        authenticated_headers = {**headers, **authorized}
        notification = await session.http.post("/mcp", headers=authenticated_headers, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        assert notification.status_code == 202
        payload = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        accepted = await session.http.post("/mcp", headers=authenticated_headers, json=payload)
        assert accepted.status_code == 200 and "slack_read" in accepted.text
        assert await session.credentials.revoke(_ADMIN, session.agent_id)
        for next_headers in (authenticated_headers, headers):
            response = await session.http.post("/mcp", headers=next_headers, json=payload)
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_enabled_portable_submission_never_accepts_agent_credentials(tmp_path: Path) -> None:
    async with _agent_session(tmp_path, "flat", stateless=False) as session:
        await create_system_settings_service(session.database).set_portable_connectors_enabled(
            "administrator", UpdatePortableConnectorSettings(portable_connectors_enabled=True),
        )
        name = "portable_connector_submit_revision"
        assert name not in {tool.name for tool in await session.client.list_tools()}
        result = await session.client.call_tool(
            name, {"draft_id": str(uuid4()), "revision_id": str(uuid4())}, raise_on_error=False,
        )
        assert result.is_error
        assert result.structured_content is None
