from pathlib import Path

import pytest

from test_routes_acceptance import (
    _downstream_client_with_tool, connector_availability as connector_availability,
)


@pytest.mark.asyncio
async def test_shared_downstream_catalogue_uses_explicit_grants_and_current_activation(tmp_path: Path) -> None:
    client, connector_id = await _downstream_client_with_tool(tmp_path)
    with client:
        url = f"/api/admin/connectors/mcp/{connector_id}"
        client.put(url + "/publication").raise_for_status()
        client.put(url + "/tools/activation", json={"tools": [{
            "tool_id": "echo", "activation_status": "enabled",
        }]}).raise_for_status()
        permissions = "/api/admin/mcp-permissions/groups/umbod-admins/permissions"
        client.put(permissions, json={"connectors": [{
            "connector_id": connector_id, "permission_status": "enabled",
        }]}).raise_for_status()
        assert client.get("/api/me/catalogue").json()["connectors"] == []
        client.put(permissions, json={"capabilities": [{
            "connector_id": connector_id, "capability_kind": "tool", "capability_key": "echo",
            "permission_status": "enabled",
        }]}).raise_for_status()
        response = client.get("/api/me/catalogue")
        assert response.status_code == 200
        assert response.json()["connectors"] == [{
            "connector_id": connector_id, "kind": "downstream_mcp",
            "display_name": "Alpha", "capability_description": "Manage downstream tools",
            "ownership": "shared", "capabilities": [{
                "kind": "tool", "key": "echo", "name": "Echo", "description": "Echo",
            }],
        }]
        assert "https://" not in response.text
        client.put(url + "/tools/activation", json={"tools": [{
            "tool_id": "echo", "activation_status": "disabled",
        }]}).raise_for_status()
        assert client.get("/api/me/catalogue").json()["connectors"] == []
