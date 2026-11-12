import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import Request
from fastmcp import Client, FastMCP
from starlette.routing import Mount
from mcp.types import ResourceLink

from umbod.config import AppConfig
from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, ByteStream, Permission, Principal, PrincipalType, RootBootstrapGrant, RootBootstrapSpec
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.infrastructure import LocalContentConfig, create_content_driver, create_root_provisioning, create_access_control_driver
from umbod.mcp.filesystem.factory import DatabaseFilesystemServiceFactory
from umbod.mcp.filesystem.upload_sessions import FilesystemBeginUploadTool, FilesystemCompleteUploadTool
from umbod.rest.main import create_app
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .conftest import FilesystemMcp, ScopedCallerCapture, caller_snapshot
from .test_tools import METADATA, root_id


@pytest.mark.asyncio
async def test_begin_complete_resource_link_and_owner_isolation(filesystem_invocation_mcp: FilesystemMcp) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        before = datetime.now(timezone.utc)
        begin = await client.call_tool("filesystem_begin_upload", {
            "parent_id": await root_id(client), "name": "session", "metadata": METADATA,
            "size_bytes": 1, "expected_sha256": hashlib.sha256(b"x").hexdigest(),
        })
        data = begin.structured_content
        assert data["complete_tool"] == "filesystem_complete_upload"
        assert data["transfer"]["type"] == "single"
        assert data["transfer"]["method"] == "PUT"
        assert data["transfer"]["url"] == f"https://api.example/api/filesystem/uploads/{data['upload_id']}/transfer"
        expiry = datetime.fromisoformat(data["expires_at"])
        assert before + timedelta(minutes=14) < expiry < before + timedelta(minutes=16)
        await filesystem.services.upload_sessions().put_delegated(
            UUID(data["upload_id"]), data["transfer"]["headers"]["X-Umbod-Upload-Token"],
            "application/octet-stream", byte_stream(b"x"),
        )
        complete = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]})
        retry = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]})
        assert retry.structured_content == complete.structured_content
        assert complete.structured_content["sha256"] == hashlib.sha256(b"x").hexdigest()
        assert complete.structured_content["size_bytes"] == 1
        rendered = json.loads(complete.content[0].text)
        assert rendered == complete.structured_content
        assert rendered["node"]["permissions"]["can_write"] is True
        assert rendered["node"]["visible_to"]["type"] == "available"
        assert "sharing" in complete.structured_content["node"]
        assert complete.structured_content["node"]["visible_to"]["grants"] == []
        policies = create_access_control_driver(database=filesystem.database)
        grant = AccessGrant(
            node_id=UUID(complete.structured_content["node"]["id"]),
            principal=Principal(type=PrincipalType.USER, issuer="foreign", id="unregistered"),
            permissions={Permission.READ}, recursive=True,
        )
        await policies.add_grant(grant)
        current = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]})
        assert current.structured_content["node"]["visible_to"]["grants"] == [grant.model_dump(mode="json")]
        assert current.structured_content["node"]["sharing"]["grants"] == []
        assert current.structured_content["node"]["id"] == complete.structured_content["node"]["id"]
        assert current.structured_content["sha256"] == complete.structured_content["sha256"]
        assert any(isinstance(block, ResourceLink) for block in complete.content)
        filesystem.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        denied = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]}, raise_on_error=False)
        assert denied.is_error
        assert "filesystem_permission_denied" in denied.content[0].text


async def byte_stream(payload: bytes) -> ByteStream:
    yield payload


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [b"", b"\x00\xff\xfe", b"x" * (10_485_760 + 1)], ids=["empty", "binary", "above-inline-cap"])
async def test_shared_inmemory_local_storage_mcp_begin_capability_only_rest_put_mcp_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes,
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    content_config = LocalContentConfig(type="local", directory=tmp_path / "content")
    settings = AppConfig(
        rest={"metrics_enabled": False}, runtime={"profile": "test"},
        connector_store={"type": "inmemory"},
        filesystem={"content": {"type": "local", "directory": str(content_config.directory)}, "upload_max_bytes": 20_971_520},
    )
    app = create_app(settings, [])
    transfer_app = next(route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/filesystem")
    captured: list[ConnectorApiDependencyFactories] = []

    def capture_factories(request: Request) -> ConnectorApiDependencyFactories:
        factories = get_connector_api_dependency_factories(request)
        captured.append(factories)
        return factories

    transfer_app.dependency_overrides[get_connector_api_dependency_factories] = capture_factories
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost", follow_redirects=False,
    ) as rest:
        await rest.put(f"/api/filesystem/uploads/{UUID(int=0)}/transfer", content=b"")
        runtime = captured[0].persistence_runtime
        await create_root_provisioning(database=runtime.database).provision(RootBootstrapSpec(grants=(
            RootBootstrapGrant(
                principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="alice"),
                permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
            ),
        )))
        services = DatabaseFilesystemServiceFactory(
            runtime.database, create_content_driver(content_config), 20_971_520, "https://issuer", "http://localhost", max_read_bytes=1_048_576)
        callers = ScopedCallerCapture()
        callers.current.set(caller_snapshot("alice", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED))
        server = FastMCP()
        server.add_tool(FilesystemBeginUploadTool(callers, services))
        server.add_tool(FilesystemCompleteUploadTool(callers, services))
        async with Client(server) as mcp:
            begin = await mcp.call_tool("filesystem_begin_upload", {
                "parent_id": str(ROOT_ID), "name": "shared", "metadata": METADATA,
                "size_bytes": len(payload), "expected_sha256": hashlib.sha256(payload).hexdigest(),
            })
            transfer = begin.structured_content["transfer"]
            url = transfer["url"]
            missing = await rest.put(url, content=b"forbidden")
            wrong = await rest.put(url, headers={"X-Umbod-Upload-Token": "x" * 43}, content=b"forbidden")
            assert missing.status_code == wrong.status_code == 403
            assert missing.json() == wrong.json()
            assert missing.headers["cache-control"] == "no-store"
            assert (await rest.get(url, headers=transfer["headers"])).status_code == 401
            complete_path = f"/api/me/filesystem/uploads/{begin.structured_content['upload_id']}/complete"
            assert (await rest.post(complete_path, headers=transfer["headers"])).status_code == 401
            response = await rest.put(url, headers=transfer["headers"], content=payload)
            assert response.status_code == 204, response.text
            assert response.headers["cache-control"] == "no-store"
            assert (await rest.put(url, headers=transfer["headers"], content=payload)).status_code == 409
            complete = await mcp.call_tool("filesystem_complete_upload", {"upload_id": begin.structured_content["upload_id"]})
            retry = await mcp.call_tool("filesystem_complete_upload", {"upload_id": begin.structured_content["upload_id"]})
            assert retry.structured_content == complete.structured_content
            assert complete.structured_content["size_bytes"] == len(payload)
            assert complete.structured_content["sha256"] == hashlib.sha256(payload).hexdigest()
            assert any(isinstance(block, ResourceLink) for block in complete.content)
