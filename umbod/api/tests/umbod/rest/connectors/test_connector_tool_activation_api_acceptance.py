import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app

ACTIVATION_PATH = "/admin/connectors/catalog/test/tools/activation"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return TestClient(create_app())


def test_native_openapi_exposes_consolidated_activation_route(client: TestClient) -> None:
    paths = client.get("/admin/openapi.json").json()["paths"]
    assert set(paths["/connectors/catalog/{connector_id}/tools/activation"]) == {"get", "put"}
    assert "/connectors/catalog/{connector_id}/tools/{tool_id}/activation" not in paths
    assert "/connectors/catalog/{connector_id}/tools/invocation-policy" not in paths


def test_admin_lists_connector_tools_with_disabled_default_activation(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/test/tools")

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "test",
        "tools": [
            {"tool_id": "get_default_response", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 0},
            {"tool_id": "echo", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 0},
        ],
    }


def test_admin_enables_one_connector_tool(client: TestClient) -> None:
    response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "test",
        "tools": [
            {"tool_id": "echo", "activation_status": "enabled", "invocation_mode": "direct", "policy_revision": 0},
        ],
    }

    tools_response = client.get("/admin/connectors/catalog/test/tools")
    assert tools_response.status_code == 200
    assert _tool_by_operation_name(tools_response.json(), "get_default_response") == {
        "tool_id": "get_default_response",
        "activation_status": "disabled",
        "invocation_mode": "direct",
        "policy_revision": 0,
    }
    assert _tool_by_operation_name(tools_response.json(), "echo") == {
        "tool_id": "echo",
        "activation_status": "enabled",
        "invocation_mode": "direct",
        "policy_revision": 0,
    }


def test_admin_bulk_updates_connector_tools_in_request_order(client: TestClient) -> None:
    response = client.put(
        ACTIVATION_PATH,
        json={
            "tools": [
                {"tool_id": "echo", "activation_status": "enabled"},
                {"tool_id": "get_default_response", "activation_status": "enabled"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "test",
        "tools": [
            {"tool_id": "echo", "activation_status": "enabled", "invocation_mode": "direct", "policy_revision": 0},
            {"tool_id": "get_default_response", "activation_status": "enabled", "invocation_mode": "direct", "policy_revision": 0},
        ],
    }


def test_native_activation_route_supports_partial_and_combined_updates(client: TestClient) -> None:
    policy_only = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "invocation_mode": "ask", "expected_policy_revision": 0}]})
    activation_only = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]})
    combined = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "activation_status": "disabled", "invocation_mode": "direct", "expected_policy_revision": 1}]})

    assert _tool_by_operation_name(policy_only.json(), "echo") == {"tool_id": "echo", "activation_status": "disabled", "invocation_mode": "ask", "policy_revision": 1}
    assert _tool_by_operation_name(activation_only.json(), "echo") == {"tool_id": "echo", "activation_status": "enabled", "invocation_mode": "ask", "policy_revision": 1}
    assert _tool_by_operation_name(combined.json(), "echo") == {"tool_id": "echo", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 2}


def test_native_activation_route_revision_validation_and_atomicity(client: TestClient) -> None:
    direct = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "invocation_mode": "direct", "expected_policy_revision": 0}]})
    stale = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "invocation_mode": "ask", "expected_policy_revision": 1}]})
    unknown = client.put(ACTIVATION_PATH, json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}, {"tool_id": "missing", "invocation_mode": "ask", "expected_policy_revision": 0}]})

    assert direct.json()["tools"][0]["policy_revision"] == 0
    assert stale.status_code == 409
    assert stale.json() == {"code": "invocation_policy_revision_conflict", "conflicts": [{"tool_id": "echo", "expected_revision": 1, "current_mode": "direct", "current_revision": 0}]}
    assert unknown.status_code == 404
    retained = client.get(ACTIVATION_PATH).json()["tools"][0]
    assert retained["activation_status"] == "disabled"
    assert retained["policy_revision"] == 0


@pytest.mark.parametrize("item", [{"tool_id": "echo"}, {"tool_id": "echo", "invocation_mode": "ask"}, {"tool_id": "echo", "expected_policy_revision": 0}, {"tool_id": "echo", "invocation_mode": "ask", "expected_policy_revision": -1}])
def test_native_activation_route_rejects_malformed_partial_items(client: TestClient, item: dict[str, Any]) -> None:
    response = client.put(ACTIVATION_PATH, json={"tools": [item]})
    assert response.status_code == 422


def test_admin_bulk_update_leaves_omitted_tools_unchanged(client: TestClient) -> None:
    client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "get_default_response", "activation_status": "enabled"}]},
    )

    response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )

    assert response.status_code == 200
    tools_response = client.get("/admin/connectors/catalog/test/tools")
    assert (
        _tool_by_operation_name(tools_response.json(), "get_default_response")["activation_status"]
        == "enabled"
    )


def test_admin_bulk_update_rejects_empty_tools(client: TestClient) -> None:
    response = client.put(ACTIVATION_PATH, json={"tools": []})

    assert response.status_code == 422


def test_admin_bulk_update_rejects_duplicate_operation_names(client: TestClient) -> None:
    response = client.put(
        ACTIVATION_PATH,
        json={
            "tools": [
                {"tool_id": "echo", "activation_status": "enabled"},
                {"tool_id": "echo", "activation_status": "disabled"},
            ]
        },
    )

    assert response.status_code == 422


def test_admin_bulk_update_unknown_tool_writes_nothing(client: TestClient) -> None:
    response = client.put(
        ACTIVATION_PATH,
        json={
            "tools": [
                {"tool_id": "echo", "activation_status": "enabled"},
                {"tool_id": "missing", "activation_status": "enabled"},
            ]
        },
    )

    assert response.status_code == 404
    tools_response = client.get("/admin/connectors/catalog/test/tools")
    assert _tool_by_operation_name(tools_response.json(), "echo")["activation_status"] == "disabled"


def test_admin_bulk_update_emits_events_only_for_changes_in_request_order(
    client: TestClient,
) -> None:
    client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )
    initial_events = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.capability_activation.changed"
    ).json()
    response = client.put(
        ACTIVATION_PATH,
        json={
            "tools": [
                {"tool_id": "echo", "activation_status": "enabled"},
                {"tool_id": "get_default_response", "activation_status": "enabled"},
            ]
        },
    )
    events = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.capability_activation.changed"
    ).json()

    assert response.status_code == 200
    assert len(events) == len(initial_events) + 1
    assert events[-1]["event"]["metadata"] == {
        "connector_kind": "native",
        "connector_id": "test",
        "capability_kind": "tool",
        "capability_key": "get_default_response",
    }


def test_admin_disables_one_connector_tool(client: TestClient) -> None:
    client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )

    response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "disabled"}]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "test",
        "tools": [
            {"tool_id": "echo", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 0},
        ],
    }

    tools_response = client.get("/admin/connectors/catalog/test/tools")
    assert tools_response.status_code == 200
    assert _tool_by_operation_name(tools_response.json(), "echo") == {
        "tool_id": "echo",
        "activation_status": "disabled",
        "invocation_mode": "direct",
        "policy_revision": 0,
    }


def test_admin_enable_and_disable_emit_metadata_only_tool_activation_events(
    client: TestClient,
) -> None:
    enable_response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )
    disable_response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "disabled"}]},
    )

    events_response = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.capability_activation.changed"
    )

    assert enable_response.status_code == 200
    assert disable_response.status_code == 200
    assert events_response.status_code == 200
    assert [stream_event["event"]["event_type"] for stream_event in events_response.json()] == [
        "connector.capability_activation.changed",
        "connector.capability_activation.changed",
    ]
    assert [stream_event["event"]["metadata"] for stream_event in events_response.json()] == [
        {
            "connector_kind": "native",
            "connector_id": "test",
            "capability_kind": "tool",
            "capability_key": "echo",
        },
        {
            "connector_kind": "native",
            "connector_id": "test",
            "capability_kind": "tool",
            "capability_key": "echo",
        },
    ]
    assert [stream_event["event"]["subject"] for stream_event in events_response.json()] == [
        "connector:native:test:tool:echo",
        "connector:native:test:tool:echo",
    ]
    assert all(
        "status" not in stream_event["event"]["metadata"] for stream_event in events_response.json()
    )
    assert all(
        "activation_status" not in stream_event["event"]["metadata"]
        for stream_event in events_response.json()
    )


def test_system_connector_tool_runtime_state_returns_latest_activation_status(
    client: TestClient,
) -> None:
    initial_response = client.get("/system/connectors/test/tool/echo")
    enable_response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )
    enabled_state_response = client.get("/system/connectors/test/tool/echo")
    disable_response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "disabled"}]},
    )
    disabled_state_response = client.get("/system/connectors/test/tool/echo")

    assert initial_response.status_code == 200
    assert initial_response.json() == {
        "connector_id": "test",
        "operation_name": "echo",
        "status": "disabled",
    }
    assert enable_response.status_code == 200
    assert enabled_state_response.status_code == 200
    assert enabled_state_response.json() == {
        "connector_id": "test",
        "operation_name": "echo",
        "status": "enabled",
    }
    assert disable_response.status_code == 200
    assert disabled_state_response.status_code == 200
    assert disabled_state_response.json() == {
        "connector_id": "test",
        "operation_name": "echo",
        "status": "disabled",
    }


def test_admin_filters_connector_tools_by_activation_status(client: TestClient) -> None:
    client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )

    enabled_response = client.get("/admin/connectors/catalog/test/tools?activation_status=enabled")
    disabled_response = client.get(
        "/admin/connectors/catalog/test/tools?activation_status=disabled"
    )

    assert enabled_response.status_code == 200
    assert enabled_response.json() == {
        "connector_id": "test",
        "tools": [{"tool_id": "echo", "activation_status": "enabled", "invocation_mode": "direct", "policy_revision": 0}],
    }
    assert disabled_response.status_code == 200
    assert disabled_response.json() == {
        "connector_id": "test",
        "tools": [{"tool_id": "get_default_response", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 0}],
    }


def test_admin_cannot_list_tools_for_unknown_connector(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/missing/tools")

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector missing was not found"}


def test_admin_cannot_enable_unknown_connector_tool(client: TestClient) -> None:
    response = client.put(
        ACTIVATION_PATH,
        json={"tools": [{"tool_id": "missing_tool", "activation_status": "enabled"}]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector tool was not found"}


def _tool_by_operation_name(body: dict[str, Any], operation_name: str) -> dict[str, Any]:
    return next(tool for tool in body["tools"] if tool["tool_id"] == operation_name)
