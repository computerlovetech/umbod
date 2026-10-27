from urllib.parse import quote

import httpx
import pytest

from conftest import RuntimeEndpoints
from umbod.core.admin_overview.models import AdminOverview, Available, ConnectorCounts, ToolCounts


@pytest.mark.parametrize("kind,path,identity_field", [
    ("catalog", "catalog", "id"),
    ("openapi", "openapi", "connector_id"),
    ("mcp", "mcp", "connector_id"),
])
def test_running_overview_matches_inventory_and_activation_counts(
    runtime_endpoints: RuntimeEndpoints, kind: str, path: str, identity_field: str,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        response = client.get("/api/admin/overview")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        summary = AdminOverview.model_validate(response.json())
        inventory = client.get(f"/api/admin/connectors/{path}")
        assert inventory.status_code == 200, inventory.text
        connectors = inventory.json()["connectors"]
        if kind == "mcp":
            connectors = [entry for entry in connectors if entry["authorization_mode"] == "shared"]
        statuses = [entry["publication_status"] for entry in connectors]
        expected = ConnectorCounts(
            configured=len(connectors) if kind == "mcp" else len(connectors) - statuses.count("unconfigured"),
            published=statuses.count("published"),
            unconfigured=statuses.count("unconfigured"),
            draft=statuses.count("draft"),
            unpublished=statuses.count("unpublished"),
            unhealthy=sum(entry["health"]["status"] == "unhealthy" for entry in connectors) if kind == "mcp" else 0,
        )
        tools = []
        for connector in connectors:
            connector_id = quote(connector[identity_field], safe="")
            activations = client.get(f"/api/admin/connectors/{path}/{connector_id}/tools/activation")
            assert activations.status_code == 200, activations.text
            tools.extend(activations.json()["tools"])
        row = next(row for row in summary.breakdown if row.kind == kind)
        assert row.connectors == Available(status="available", value=expected)
        assert row.tools == Available(status="available", value=ToolCounts(
            known=len(tools), enabled=sum(tool["activation_status"] == "enabled" for tool in tools),
        ))


def test_running_overview_counts_registered_nonblank_permission_groups(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        response = client.get("/api/admin/overview")
        groups = client.get("/api/admin/groups")
        assert response.status_code == 200, response.text
        assert groups.status_code == 200, groups.text
        summary = AdminOverview.model_validate(response.json())
        assert summary.permission_groups == Available(
            status="available", value=sum(bool(group["group_id"].strip()) for group in groups.json()["groups"]),
        )
