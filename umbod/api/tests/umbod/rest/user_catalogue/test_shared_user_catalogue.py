import pytest

from umbod.core.connectors.downstream_mcp.models import DiscoveredServerIcon
from tests.umbod.rest.connectors.downstream_mcp.test_routes_acceptance import (
    _downstream_client_with_tool, connector_availability as connector_availability,
)


@pytest.mark.parametrize(("icon_src", "expected_icon"), [
    ("", {}),
    ("https://icons.example.test/logo.png", {"icon_url": "https://icons.example.test/logo.png"}),
    ("data:image/png;base64,aWNvbg==", {"icon_url": "data:image/png;base64,aWNvbg=="}),
    ("https://user:secret@icons.example.test/logo.png", {}),
    ("file:///tmp/logo.png", {}),
])
def test_shared_downstream_catalogue_uses_explicit_grants_and_current_activation(
    icon_src: str, expected_icon: dict[str, str],
) -> None:
    icons = (
        DiscoveredServerIcon(src=icon_src),
        DiscoveredServerIcon(src="https://icons.example.test/alternate.png"),
    ) if icon_src else ()
    client, connector_id = _downstream_client_with_tool(icons)
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
        if expected_icon:
            assert client.get(url).json()["icon_url"] == expected_icon["icon_url"]
        assert response.json()["connectors"] == [{
            "connector_id": connector_id, "kind": "downstream_mcp",
            "display_name": "Alpha", "capability_description": "Manage downstream tools",
            "ownership": "shared", "capabilities": [{
                "kind": "tool", "key": "echo", "name": "Echo", "description": "Echo",
                "input_schema": {"type": "object"}, "output_schema": {"status": "absent"},
            }],
            **expected_icon,
        }]
        client.put(url + "/tools/activation", json={"tools": [{
            "tool_id": "echo", "activation_status": "disabled",
        }]}).raise_for_status()
        assert client.get("/api/me/catalogue").json()["connectors"] == []
