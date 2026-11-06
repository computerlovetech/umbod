from contextlib import AsyncExitStack

import httpx
import pytest

from tests.umbod.mcp.integration.test_public_app_http_client import _build_public_app
from tests.umbod.mcp.test_http_transport import HEADERS, INITIALIZE, rpc_result
from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.mcp.middleware.response_metadata import RESPONSE_METADATA_KEY


@pytest.mark.asyncio
async def test_public_initialization_and_server_card_share_build_identity() -> None:
    async with AsyncExitStack() as runtime_resources:
        app, token, _context, _publishing_store = await _build_public_app(runtime_resources)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
                card = await client.get("/.well-known/mcp/server-card.json")
                initialized = await client.post("/mcp", json=INITIALIZE, headers={**HEADERS, "Authorization": f"Bearer {token}"})
                failed = await client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "echo_echo_message", "arguments": {}},
                }, headers={**HEADERS, "Authorization": f"Bearer {token}"})
    assert card.json()["version"] == UMBOD_RELEASE
    assert rpc_result(initialized)["serverInfo"]["version"] == UMBOD_RELEASE
    failure = rpc_result(failed)
    assert failure["isError"]
    assert failure["_meta"][RESPONSE_METADATA_KEY] == {
        "server_version": UMBOD_RELEASE,
        "server_revision": UMBOD_REVISION,
        "request_id": failed.headers["X-Request-ID"],
    }
    assert failed.headers["X-Request-ID"] in failure["content"][-1]["text"]
    for response in (card, initialized, failed):
        assert response.headers["X-Umbod-Version"] == UMBOD_RELEASE
        assert response.headers["X-Umbod-Revision"] == UMBOD_REVISION
