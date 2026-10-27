from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.umbod.rest.user_catalogue.query_budget_support import QueryCounts
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.schemas import AssignablePermissionTargetsResponse


AdminPermissionHttp = tuple[TestClient, FastAPI, ConnectorApiDependencyFactories, QueryCounts]


def read_assignable_targets(
    client: TestClient, counts: QueryCounts,
) -> AssignablePermissionTargetsResponse:
    counts.reset()
    response = client.get("/api/admin/mcp-permissions/assignable-targets")
    assert response.status_code == 200, response.text
    assert not counts.writes
    assert counts.schema_calls == 0
    return AssignablePermissionTargetsResponse.model_validate(response.json())


def assert_shared_targets(
    targets: AssignablePermissionTargetsResponse, keys: set[str],
) -> None:
    assert [connector.model_dump() for connector in targets.connectors] == (
        [{"connector_id": "shared", "display_name": "Shared"}] if keys else []
    )
    assert [capability.model_dump() for capability in targets.capabilities] == [
        {
            "connector_id": "shared", "capability_kind": "tool",
            "capability_key": key, "display_name": key,
        }
        for key in sorted(keys)
    ]


