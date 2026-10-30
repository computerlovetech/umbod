import base64
import json
from typing import Any
from uuid import UUID

import httpx
import pytest

from tests.umbod.mcp.test_http_transport import HEADERS, rpc_result
from umbod.mcp.http_transport import MAX_MCP_REQUEST_BODY_BYTES, create_mcp_http_app

from .conftest import FilesystemMcp
from .test_tools import METADATA

CAP = 10_485_760


async def call_tool(client: httpx.AsyncClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}).encode()
    response = await client.post("/mcp", headers=HEADERS, content=body)
    return rpc_result(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["base64", "escaped-utf8"])
async def test_ten_mib_upload_roundtrips_over_http(filesystem_mcp: FilesystemMcp, encoding: str) -> None:
    expected = b"\x00" * CAP
    content = ({"encoding": "base64", "data": base64.b64encode(expected).decode()}
               if encoding == "base64" else {"encoding": "utf-8", "text": expected.decode()})
    app = create_mcp_http_app(filesystem_mcp.server, path="/mcp", stateless_http=True,
                              max_request_body_bytes=MAX_MCP_REQUEST_BODY_BYTES)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            root = await call_tool(client, "get_filesystem_root", {})
            before = filesystem_mcp.callers.count
            result = await call_tool(client, "filesystem_upload", {
                "parent_id": root["structuredContent"]["id"], "name": "uploaded", "metadata": METADATA,
                "content": content,
            })
    assert not result.get("isError", False)
    assert result["content"][0]["text"] == "File uploaded successfully."
    assert filesystem_mcp.callers.count == before + 1
    assert filesystem_mcp.content.put_count == 1
    download = await filesystem_mcp.files.open_download(
        filesystem_mcp.callers.current.get(), UUID(result["structuredContent"]["id"]),
    )
    assert b"".join([chunk async for chunk in download.data]) == expected


@pytest.mark.asyncio
async def test_oversize_decoded_upload_reaches_safe_tool_error_over_http(filesystem_mcp: FilesystemMcp) -> None:
    app = create_mcp_http_app(filesystem_mcp.server, path="/mcp", stateless_http=True,
                              max_request_body_bytes=MAX_MCP_REQUEST_BODY_BYTES)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            root = await call_tool(client, "get_filesystem_root", {})
            before = filesystem_mcp.callers.count
            result = await call_tool(client, "filesystem_upload", {
                "parent_id": root["structuredContent"]["id"], "name": "uploaded", "metadata": METADATA,
                "content": {"encoding": "base64", "data": base64.b64encode(b"x" * (CAP + 1)).decode()},
            })
    assert result["isError"]
    assert result["content"][0]["text"] == "filesystem_upload_too_large: Filesystem upload too large"
    assert filesystem_mcp.callers.count == before
    assert filesystem_mcp.content.put_count == 0
