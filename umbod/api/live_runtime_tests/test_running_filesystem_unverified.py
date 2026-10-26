from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints


@pytest.mark.asyncio
async def test_local_rest_test_user_respects_policy_while_mcp_requires_verified_identity(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    base = "/api/me/filesystem"
    policy_path = "/api/admin/filesystem/root-access"
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as rest:
        user = rest.get("/api/admin/users")
        assert user.status_code == 200
        root = rest.get(base + "/root")
        assert root.status_code == 403
        assert root.json()["detail"]["code"] == "filesystem_permission_denied"
        assert root.headers["cache-control"] == "no-store"
        inspected = rest.get(policy_path)
        assert inspected.status_code == 200
        policy = inspected.json()
        assert policy["suggested_issuer"] == "urn:umbod:local"
        assert policy["groups"] == []
        configured = rest.put(policy_path, json={
            "expected_revision": policy["revision"],
            "groups": [{
                "issuer": policy["suggested_issuer"], "group_id": "admin",
                "permissions": ["discover", "write"],
            }],
        })
        assert configured.status_code == 200, configured.text
        try:
            root = rest.get(base + "/root")
            assert root.status_code == 200, root.text
            created = rest.post(base + "/nodes/" + root.json()["id"] + "/directories", json={
                "name": "local-test-private-" + uuid4().hex,
                "metadata": {"content_type": {}, "attributes": {}},
            })
            assert created.status_code == 201, created.text
            child = created.json()
            assert rest.get(base + "/nodes/" + child["id"]).json() == child
            listing = rest.get(base + "/nodes/" + root.json()["id"] + "/children")
            assert listing.status_code == 200
            assert child["id"] in {node["id"] for node in listing.json()["nodes"]}
            unimplemented = rest.get(base + "/nodes", params={"scope": "owned"})
            assert unimplemented.status_code == 501
            assert unimplemented.headers["cache-control"] == "no-store"
            headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
            client: Client[Any] = Client(StreamableHttpTransport(runtime_endpoints.mcp_url, headers=headers))
            async with client:
                result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
                assert result.is_error
                assert "filesystem_permission_denied" in result.content[0].text
        finally:
            current = rest.get(policy_path)
            assert current.status_code == 200
            revoked = rest.put(policy_path, json={
                "expected_revision": current.json()["revision"], "groups": [],
            })
            assert revoked.status_code == 200, revoked.text
        assert rest.get(base + "/root").status_code == 403
        assert rest.get(base + "/nodes/" + child["id"]).json() == child
