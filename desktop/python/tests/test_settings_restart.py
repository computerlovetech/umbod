"""Exercise saved settings through fresh host processes, real MCP and durable SQL."""

import asyncio
import json
import socket
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from umbod_desktop.security import DESKTOP_GROUP


@asynccontextmanager
async def process_backend(directory):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "umbod_desktop.main",
        "serve",
        "--profile",
        "dev",
        "--data-dir",
        str(directory),
        "--test-credentials",
        "--persistent",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 45))
        assert "error" not in ready, ready
        origin = "http://" + ready["management"]
        async with httpx.AsyncClient(
            base_url=origin,
            headers={"Authorization": "Bearer " + ready["admin_token"]},
            timeout=30,
        ) as client:
            assert (await client.get("/desktop/health")).json()["status"] == "ok"
            yield client, origin, ready["pid"]
            assert (await client.post("/desktop/shutdown")).status_code == 200
        assert await asyncio.wait_for(process.wait(), 30) == 0
    finally:
        if process.returncode is None:
            process.terminate()
            await asyncio.wait_for(process.wait(), 15)


async def test_modes_and_administration_survive_real_process_restarts():
    with tempfile.TemporaryDirectory(prefix="umbod-test-settings-") as temporary:
        directory = Path(temporary)
        fixture = directory / "fixture.py"
        fixture.write_text(
            "from fastmcp import FastMCP\nm=FastMCP('fixture')\n@m.tool\ndef echo(message: str) -> str: return message\nm.run(show_banner=False)\n"
        )
        async with process_backend(directory) as (client, origin, pid):
            prepared = await client.post(
                "/desktop/upstreams",
                json={
                    "name": "Saved",
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(fixture)],
                },
            )
            assert prepared.status_code == 200, prepared.text
            created = await client.post(
                "/api/admin/connectors/mcp",
                json={
                    "metadata": {
                        "display_name": "Saved",
                        "capability_description": "Fixture tools",
                        "public_path": "/mcp/proxies/saved",
                    },
                    "configuration": prepared.json()["configuration"],
                },
            )
            assert created.status_code == 201, created.text
            identifier = created.json()["connector_id"]
            assert (
                await client.put(
                    f"/desktop/upstreams/{prepared.json()['host_id']}/binding",
                    json={"connector_id": identifier},
                )
            ).status_code == 200
            base = f"/api/admin/connectors/mcp/{identifier}"
            assert (await client.post(base + "/discoveries")).status_code == 200
            assert (await client.put(base + "/publication")).status_code == 200
            assert (
                await client.put(
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
            ).status_code == 200
            assert (
                await client.post(f"/api/admin/mcp-permissions/groups/{DESKTOP_GROUP}")
            ).status_code in (200, 201)
            permissions = (
                f"/api/admin/mcp-permissions/groups/{DESKTOP_GROUP}/permissions"
            )
            assert (
                await client.put(
                    permissions,
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
            ).status_code == 200
            # Credential payloads never enter host settings and must not be rotated.
            assert (
                await client.put(
                    "/desktop/credentials/upstream:preserved",
                    json={"value": "fixture-secret"},
                )
            ).status_code == 200
            baseline = (await client.get(base)).json()
            grants = (await client.get(permissions)).json()
            first = {
                "connector_tool_exposure_mode": "flat",
                "mcp_administrator_enabled": False,
            }
            assert (await client.put("/desktop/settings", json=first)).json()[
                "restart_required"
            ]
        credentials = (directory / "fixture-credentials.json").read_bytes()
        state_before_failure = (directory / "desktop-v2.json").read_bytes()
        # Force a real failed startup on the saved port, then recover without
        # resetting any profile state or changing the selected settings.
        port = json.loads((directory / "python-endpoint.json").read_text())["port"]
        with socket.socket() as conflict:
            conflict.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            conflict.bind(("127.0.0.1", port))
            conflict.listen(1)
            failed = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "umbod_desktop.main",
                "serve",
                "--profile",
                "dev",
                "--data-dir",
                str(directory),
                "--test-credentials",
                "--persistent",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await asyncio.wait_for(failed.communicate(), 45)
            assert failed.returncode == 1
            assert "error" in json.loads(output)
        assert (directory / "desktop-v2.json").read_bytes() == state_before_failure
        assert (directory / "fixture-credentials.json").read_bytes() == credentials
        previous_pid = pid
        cases = [
            ("flat", False),
            ("gateway", True),
            ("codemode", True),
            ("gateway", False),
        ]
        for index, (mode, admin) in enumerate(cases):
            async with process_backend(directory) as (client, origin, pid):
                assert pid != previous_pid
                previous_pid = pid
                selected = {
                    "connector_tool_exposure_mode": mode,
                    "mcp_administrator_enabled": admin,
                }
                assert (await client.get("/desktop/settings")).json() == {
                    "pending": selected,
                    "effective": selected,
                    "restart_required": False,
                }
                restored = (await client.get(base)).json()
                assert {k: v for k, v in restored.items() if k != "health"} == {
                    k: v for k, v in baseline.items() if k != "health"
                }
                assert (await client.get(permissions)).json() == grants
                token = json.loads(credentials)["python:agent-token"]
                for method in ("GET", "PUT"):
                    denied = await client.request(
                        method,
                        "/desktop/settings",
                        headers={"Authorization": "Bearer " + token},
                        json=selected,
                    )
                    assert denied.status_code == 401
                async with Client(
                    StreamableHttpTransport(
                        origin + "/mcp", headers={"Authorization": "Bearer " + token}
                    )
                ) as agent:
                    expected = (
                        {"Saved_echo"}
                        if mode == "flat"
                        else {
                            "search_tools",
                            "execute_tool" if mode == "gateway" else "execute_code",
                        }
                    )
                    if admin:
                        expected |= {
                            "read_connector_configuration",
                            "upsert_connector_configuration",
                        }
                    async with asyncio.timeout(20):
                        while {
                            tool.name for tool in await agent.list_tools()
                        } != expected:
                            await asyncio.sleep(0.1)
                    if mode == "flat":
                        assert "persisted" in str(
                            await agent.call_tool(
                                "Saved_echo", {"message": "persisted"}
                            )
                        )
                    elif mode == "gateway":
                        assert "persisted" in str(
                            await agent.call_tool(
                                "execute_tool",
                                {
                                    "tool_name": "Saved_echo",
                                    "arguments": {"message": "persisted"},
                                },
                            )
                        )
                    else:
                        result = await agent.call_tool(
                            "search_tools", {"query": "echo"}
                        )
                        assert "Saved_echo" in str(result)
                    if admin:
                        # Successful invocation proves desktop-owner authorization,
                        # not merely registration of the administrator names.
                        result = await agent.call_tool(
                            "read_connector_configuration",
                            {
                                "connector_kind": "downstream_mcp",
                                "connector_id": identifier,
                            },
                        )
                        assert not result.is_error
                if index + 1 < len(cases):
                    next_mode, next_admin = cases[index + 1]
                    saved = await client.put(
                        "/desktop/settings",
                        json={
                            "connector_tool_exposure_mode": next_mode,
                            "mcp_administrator_enabled": next_admin,
                        },
                    )
                    assert saved.json()["effective"] == selected
                    assert saved.json()["restart_required"]
            assert (directory / "fixture-credentials.json").read_bytes() == credentials
