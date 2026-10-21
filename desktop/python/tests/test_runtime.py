import asyncio
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from umbod.mcp.agent_instructions import AGENT_INSTRUCTIONS, AGENT_INSTRUCTIONS_URI

from umbod_desktop.backward_compatibility.adapters.administration import (
    BackendPrefixRepair,
)
from umbod_desktop.backward_compatibility.tool_names import DesktopToolNames
from umbod_desktop.runtime import create_desktop_app
from umbod_desktop.security import DESKTOP_GROUP, persistent_secret
from umbod_desktop.storage import DesktopState


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def set(self, reference: str, value: str) -> None:
        self.values[reference] = value

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


async def discovered_names(agent):
    result = await agent.call_tool("search_tools", {"query": "echo"})
    return {match["tool_name"] for match in result.structured_content["matches"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["http", "stdio", "legacy_stdio"])
async def test_shared_backend_connector_flow(tmp_path: Path, transport: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = FastMCP("fixture")

    @fixture.tool
    def echo(message: str) -> str:
        return message

    fixture_app = fixture.http_app(path="/mcp")
    vault = MemoryVault()
    with socket.socket() as listener, socket.socket() as upstream:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app, token = await create_desktop_app(
            tmp_path, "dev", origin, vault, lambda: None
        )
        servers = [
            uvicorn.Server(uvicorn.Config(app, log_level="error")),
            uvicorn.Server(uvicorn.Config(fixture_app, log_level="error")),
        ]
        tasks = [
            asyncio.create_task(server.serve(sockets=[sock]))
            for server, sock in zip(servers, [listener, upstream])
        ]
        try:
            async with asyncio.timeout(30):
                while not all(server.started for server in servers):
                    for task in tasks:
                        if task.done():
                            await task
                    await asyncio.sleep(0.02)
            async with httpx.AsyncClient(
                base_url=origin,
                headers={"Authorization": f"Bearer {token}"},
                # This client sits idle while a separate MCP client discovers and
                # invokes tools. HTTPX and Uvicorn both default to a five-second
                # keep-alive expiry, so reusing that socket can race server close.
                # Use fresh management connections; keep every behavior assertion
                # and let transport failures fail immediately (no retry masking).
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as client:
                assert (await client.get("/desktop/health")).status_code == 200
                assert (
                    await client.get(
                        "/desktop/health", headers={"Authorization": "Bearer wrong"}
                    )
                ).status_code == 401
                assert (await client.get("/api/admin/users")).json()[
                    "id"
                ] == "desktop-owner"
                draft = {
                    "name": "Fixture",
                    "transport": "http",
                    "url": f"http://127.0.0.1:{upstream.getsockname()[1]}/mcp",
                }
                if transport in ("stdio", "legacy_stdio"):
                    script = tmp_path / "fixture.py"
                    script.write_text(
                        "from fastmcp import FastMCP\nmcp=FastMCP('fixture')\n@mcp.tool\ndef echo(message: str) -> str: return message\nmcp.run(transport='stdio', show_banner=False)\n"
                    )
                    draft = {
                        "name": "Fixture",
                        "transport": "stdio",
                        "command": sys.executable,
                        "args": [str(script)],
                    }
                if transport == "legacy_stdio":
                    draft["args"] = [
                        str(
                            Path(__file__).resolve().parents[2]
                            / "scripts/fixture_stdio.py"
                        )
                    ]
                prepared = await client.post("/desktop/upstreams", json=draft)
                assert prepared.status_code == 200, prepared.text
                created = await client.post(
                    "/api/admin/connectors/mcp",
                    json={
                        "metadata": {
                            "display_name": "Fixture",
                            "capability_description": "Fixture tools",
                            "public_path": "/mcp/proxies/desktop-46b824c3-b082-4a1a-8177-c2c096eec4ce",
                        },
                        "configuration": prepared.json()["configuration"],
                    },
                )
                assert created.status_code == 201, created.text
                assert created.json()["tool_name_prefix"] == "Fixture"
                identifier = created.json()["connector_id"]
                assert (await client.put(
                    f"/desktop/upstreams/{prepared.json()['host_id']}/binding",
                    json={"connector_id": identifier},
                )).status_code == 200
                base = f"/api/admin/connectors/mcp/{identifier}"
                discovered = await client.post(base + "/discoveries")
                assert discovered.status_code == 200, discovered.text
                assert (await client.put(base + "/publication")).status_code == 200
                tools = (await client.get(base + "/tools")).json()["tools"]
                assert tools[0]["activation_status"] == "disabled"
                result = await client.put(
                    base + "/tools/activation",
                    json={
                        "tools": [
                            {
                                "tool_id": "echo",
                                "activation_status": "enabled",
                                "invocation_mode": "direct",
                                "expected_policy_revision": 0,
                            }
                        ]
                    },
                )
                assert result.status_code == 200, result.text
                await client.post(f"/api/admin/mcp-permissions/groups/{DESKTOP_GROUP}")
                result = await client.put(
                    f"/api/admin/mcp-permissions/groups/{DESKTOP_GROUP}/permissions",
                    json={
                        "capabilities": [
                            {
                                "connector_id": identifier,
                                "capability_kind": "tool",
                                "capability_key": "echo",
                                "permission_status": "enabled",
                            }
                        ]
                    },
                )
                assert result.status_code == 200, result.text
                agent_token = persistent_secret(vault, "python:agent-token")
                async with Client(
                    StreamableHttpTransport(
                        origin + "/mcp",
                        headers={"Authorization": f"Bearer {agent_token}"},
                    )
                ) as first_agent:
                    resources = await first_agent.list_resources()
                    setup = next(resource for resource in resources if str(resource.uri) == AGENT_INSTRUCTIONS_URI)
                    assert setup.mime_type == "text/markdown"
                    contents = await first_agent.read_resource(AGENT_INSTRUCTIONS_URI)
                    assert contents[0].text == AGENT_INSTRUCTIONS
                    assert await first_agent.list_prompts() == []
                    async with asyncio.timeout(15):
                        while not await discovered_names(first_agent):
                            await asyncio.sleep(0.1)
                # Adding another connector must not hide its enabled tools behind
                # a runtime catalog or permission snapshot from the first connector.
                second = await client.post(
                    "/api/admin/connectors/mcp",
                    json={
                        "metadata": {
                            "display_name": "Second fixture",
                            "tool_name_prefix": "second",
                            "capability_description": "Second fixture tools",
                            "public_path": "/mcp/proxies/second",
                        },
                        "configuration": prepared.json()["configuration"],
                    },
                )
                assert second.status_code == 201, second.text
                second_id = second.json()["connector_id"]
                second_base = f"/api/admin/connectors/mcp/{second_id}"
                assert (
                    await client.put(second_base + "/publication")
                ).status_code == 200
                assert (
                    await client.put(
                        second_base + "/tools/activation",
                        json={
                            "tools": [
                                {"tool_id": "echo", "activation_status": "enabled"}
                            ]
                        },
                    )
                ).status_code == 200
                assert (
                    await client.put(
                        f"/api/admin/mcp-permissions/groups/{DESKTOP_GROUP}/permissions",
                        json={
                            "capabilities": [
                                {
                                    "connector_id": second_id,
                                    "capability_kind": "tool",
                                    "capability_key": "echo",
                                    "permission_status": "enabled",
                                }
                            ]
                        },
                    )
                ).status_code == 200
                agent_token = persistent_secret(vault, "python:agent-token")
                async with Client(
                    StreamableHttpTransport(
                        origin + "/mcp",
                        headers={"Authorization": f"Bearer {agent_token}"},
                    )
                ) as agent:
                    async with asyncio.timeout(15):
                        assert {tool.name for tool in await agent.list_tools()} == {"search_tools", "execute_tool"}
                        while len(await discovered_names(agent)) != 2:
                            await asyncio.sleep(0.1)
                    result = await agent.call_tool(
                        "execute_tool",
                        {"tool_name": "Fixture_echo", "arguments": {
                            "text"
                            if transport == "legacy_stdio"
                            else "message": "hello python"
                        }},
                    )
                    assert "hello python" in str(result)
                    state = (await client.get("/desktop/state")).json()
                    assert state["tool_usage"][f"{identifier}.echo"]["succeeded"] == 1
                    assert (
                        "hello python" not in (tmp_path / "desktop-v2.json").read_text()
                    )
                    # Simulate a saved UUID prefix, then repair it through the
                    # real API without changing activation or permission grants.
                    legacy_prefix = "desktop_46b824c3_b082_4a1a_8177_c2c096eec4ce"
                    assert (await client.patch(
                        base, json={"tool_name_prefix": legacy_prefix}
                    )).status_code == 200
                    async with asyncio.timeout(15):
                        while legacy_prefix + "_echo" not in await discovered_names(agent):
                            await asyncio.sleep(0.1)

                    from umbod_desktop.backend_integration.administration import (
                        BackendAdministration,
                    )
                    from umbod_desktop.backend_integration.naming import (
                        BackendToolNamingPolicy,
                    )

                    administration = BackendAdministration(app, token)
                    names = DesktopToolNames(administration, BackendToolNamingPolicy(), BackendPrefixRepair(administration.client))
                    try:
                        await names.repair(DesktopState(tmp_path))
                        await names.repair(DesktopState(tmp_path))
                    finally:
                        await administration.close()
                    async with asyncio.timeout(15):
                        while "Fixture_echo" not in await discovered_names(agent):
                            await asyncio.sleep(0.1)
                    assert legacy_prefix + "_echo" not in await discovered_names(agent)
                    repaired = await agent.call_tool("execute_tool", {"tool_name": "Fixture_echo", "arguments": {
                        "text" if transport == "legacy_stdio" else "message": "after repair"
                    }})
                    assert "after repair" in str(repaired)
                    revoked = await client.put(
                        base + "/tools/activation",
                        json={
                            "tools": [
                                {"tool_id": "echo", "activation_status": "disabled"}
                            ]
                        },
                    )
                    assert revoked.status_code == 200
                    async with asyncio.timeout(15):
                        while "Fixture_echo" in await discovered_names(agent):
                            await asyncio.sleep(0.1)
                    with pytest.raises(ToolError):
                        await agent.call_tool(
                            "execute_tool",
                            {"tool_name": "Fixture_echo", "arguments": {"message": "denied"}},
                        )
                for path in (
                    "/api/admin/connectors/mcp",
                    "/system/mcp-permissions/groups",
                    "/desktop/health",
                    "/api/admin/openapi.json",
                ):
                    assert (
                        await client.get(
                            path, headers={"Authorization": "Bearer invalid"}
                        )
                    ).status_code == 401
                    assert (
                        await client.get(path, headers={"Origin": "http://example.com"})
                    ).status_code == 401
                assert (
                    await client.get(
                        "/desktop/health",
                        headers={"Authorization": f"Bearer {agent_token}"},
                    )
                ).status_code == 401

                from umbod_desktop.backend_integration.administration import (
                    BackendAdministration,
                )

                legacy = {
                    "servers": [{**draft, "id": "legacy"}],
                    "allowed_tools": ["legacy.echo"],
                    "tool_usage": {"legacy.echo": {"succeeded": 3, "failed": 1}},
                }
                source = json.dumps(legacy)
                (tmp_path / "config.json").write_text(source)
                original_discover = BackendAdministration.discover
                failed_once = False

                async def fail_discovery_once(administration: BackendAdministration, connector_id: str) -> None:
                    nonlocal failed_once
                    if not failed_once:
                        failed_once = True
                        raise OSError("fixture interrupted")
                    await original_discover(administration, connector_id)

                monkeypatch.setattr(BackendAdministration, "discover", fail_discovery_once)
                interrupted = await client.post("/desktop/migration")
                assert interrupted.json()["status"] == "needs_attention"
                resumed = await client.post("/desktop/migration")
                assert resumed.json()["status"] == "complete", resumed.text
                migrated_id = resumed.json()["connectors"]["legacy"]["id"]
                assert (tmp_path / "config.json").read_text() == source
                assert (
                    json.loads((tmp_path / "config.before-python.json").read_text())
                    == legacy
                )
                assert (await client.post("/desktop/migration")).json()[
                    "status"
                ] == "complete"
                assert (
                    len(
                        (await client.get("/api/admin/connectors/mcp")).json()[
                            "connectors"
                        ]
                    )
                    == 3
                )
                migrated_tools = (
                    await client.get(f"/api/admin/connectors/mcp/{migrated_id}/tools")
                ).json()["tools"]
                assert migrated_tools[0]["activation_status"] == "enabled"
                assert (await client.get(f"/api/admin/connectors/mcp/{migrated_id}")).json()["tool_name_prefix"] == "Fixture_2"
                assert (await client.get("/desktop/state")).json()["tool_usage"][
                    f"{migrated_id}.echo"
                ]["succeeded"] == 3
        finally:
            for server in servers:
                server.should_exit = True
            await asyncio.gather(*tasks)
