import json
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Literal, Protocol

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings
from tests.support.connector_plugins import TestConnectorPlugin


PermissionGroupChangeStatus = Literal["applied", "rejected"]


@dataclass(frozen=True)
class ConnectorCapabilityRef:
    connector_id: str
    capability_kind: str
    capability_key: str


@dataclass(frozen=True)
class ConnectorToolRef:
    connector_id: str
    operation_name: str

    def as_capability(self) -> ConnectorCapabilityRef:
        return ConnectorCapabilityRef(
            connector_id=self.connector_id,
            capability_kind="tool",
            capability_key=self.operation_name,
        )

    @classmethod
    def from_capability(cls, capability: ConnectorCapabilityRef) -> "ConnectorToolRef":
        return cls(connector_id=capability.connector_id, operation_name=capability.capability_key)


@dataclass(frozen=True)
class GroupPermissionSet:
    group_id: str
    connector_ids: tuple[str, ...]
    capabilities: tuple[ConnectorCapabilityRef, ...]

    @property
    def tools(self) -> tuple[ConnectorToolRef, ...]:
        return tuple(
            ConnectorToolRef.from_capability(capability)
            for capability in self.capabilities
            if capability.capability_kind == "tool"
        )


@dataclass(frozen=True)
class SaveGroupPermissionsRequest:
    group_id: str
    connector_ids: tuple[str, ...]
    capabilities: tuple[ConnectorCapabilityRef, ...]


@dataclass(frozen=True)
class PermissionGroupChangeResult:
    status: PermissionGroupChangeStatus
    group_id: str
    message: str | None = None


class PermissionGroupListing(Protocol):
    list_permission_groups: Callable[[], tuple[GroupPermissionSet, ...]]


class PermissionGroupReader(Protocol):
    get_permission_group: Callable[[str], GroupPermissionSet]


class PermissionGroupRegistration(Protocol):
    register_permission_group: Callable[[str], PermissionGroupChangeResult]


class PermissionGroupDeletion(Protocol):
    delete_permission_group: Callable[[str], PermissionGroupChangeResult]


@dataclass(frozen=True)
class PermissionGroupAdminPorts:
    listing: PermissionGroupListing
    reader: PermissionGroupReader
    registration: PermissionGroupRegistration
    deletion: PermissionGroupDeletion


class ExistingGroupPermissionManagement(Protocol):
    save_group_permissions: Callable[[SaveGroupPermissionsRequest], PermissionGroupChangeResult]


class McpPermissionRuntimeProbe(Protocol):
    reload_permissions: Callable[[], None]
    visible_tool_names_for_jwt_groups: Callable[[tuple[str, ...]], tuple[str, ...]]


class PermissionGroupAuthorizationProbe(Protocol):
    non_admin_can_register_permission_group: Callable[[str], bool]
    non_admin_can_delete_permission_group: Callable[[str], bool]


class RuntimePermissionLookup(Protocol):
    get_permission_group: Callable[[str], GroupPermissionSet]


class ApplicationPermissionGroupsDsl:
    def __init__(
        self,
        registry: PermissionGroupAdminPorts,
        permissions: ExistingGroupPermissionManagement,
        runtime: McpPermissionRuntimeProbe,
        authorization: PermissionGroupAuthorizationProbe,
    ) -> None:
        self.registry = registry
        self.permissions = permissions
        self.runtime = runtime
        self.authorization = authorization

    def register_empty_group(self, group_id: str) -> None:
        result = self.registry.registration.register_permission_group(group_id)

        assert result.status == "applied"
        assert self.registry.reader.get_permission_group(group_id) == GroupPermissionSet(
            group_id=group_id, connector_ids=(), capabilities=()
        )
        assert group_id in _visible_group_ids(self.registry.listing)

    def save_permission_for_new_group(self, group_id: str, tool: ConnectorToolRef) -> None:
        result = self.permissions.save_group_permissions(
            SaveGroupPermissionsRequest(
                group_id=group_id, connector_ids=(tool.connector_id,), capabilities=(tool.as_capability(),)
            )
        )

        assert result.status == "applied"
        assert self.registry.reader.get_permission_group(group_id) == GroupPermissionSet(
            group_id=group_id, connector_ids=(tool.connector_id,), capabilities=(tool.as_capability(),)
        )
        assert group_id in _visible_group_ids(self.registry.listing)

    def delete_unused_group(self, group_id: str) -> None:
        self.register_empty_group(group_id)

        result = self.registry.deletion.delete_permission_group(group_id)

        assert result.status == "applied"
        assert group_id not in _visible_group_ids(self.registry.listing)

    def register_existing_group_idempotently(self, group_id: str) -> None:
        self.register_empty_group(group_id)

        result = self.registry.registration.register_permission_group(group_id)

        assert result.status == "applied"
        assert _visible_group_ids(self.registry.listing).count(group_id) == 1
        assert self.registry.reader.get_permission_group(group_id) == GroupPermissionSet(
            group_id=group_id, connector_ids=(), capabilities=()
        )

    def register_distinct_group_values(self, first_group_id: str, second_group_id: str) -> None:
        self.register_empty_group(first_group_id)
        self.register_empty_group(second_group_id)

        assert first_group_id in _visible_group_ids(self.registry.listing)
        assert second_group_id in _visible_group_ids(self.registry.listing)
        assert self.registry.reader.get_permission_group(first_group_id) == GroupPermissionSet(
            group_id=first_group_id, connector_ids=(), capabilities=()
        )
        assert self.registry.reader.get_permission_group(second_group_id) == GroupPermissionSet(
            group_id=second_group_id, connector_ids=(), capabilities=()
        )

    def registered_empty_group_grants_no_tools(self, group_id: str) -> None:
        self.register_empty_group(group_id)
        self.runtime.reload_permissions()

        assert self.runtime.visible_tool_names_for_jwt_groups((group_id,)) == ()

    def deletion_is_rejected_for_group_with_connector_permission(
        self, group_id: str, connector_id: str
    ) -> None:
        self.permissions.save_group_permissions(
            SaveGroupPermissionsRequest(group_id=group_id, connector_ids=(connector_id,), capabilities=())
        )

        result = self.registry.deletion.delete_permission_group(group_id)

        assert result.status == "rejected"
        assert result.message == "Remove connector and capability permissions before deleting this group."
        assert self.registry.reader.get_permission_group(group_id) == GroupPermissionSet(
            group_id=group_id, connector_ids=(connector_id,), capabilities=()
        )

    def deletion_is_rejected_for_group_with_tool_permission(
        self, group_id: str, tool: ConnectorToolRef
    ) -> None:
        self.permissions.save_group_permissions(
            SaveGroupPermissionsRequest(group_id=group_id, connector_ids=(), capabilities=(tool.as_capability(),))
        )

        result = self.registry.deletion.delete_permission_group(group_id)

        assert result.status == "rejected"
        assert result.message == "Remove connector and capability permissions before deleting this group."
        assert self.registry.reader.get_permission_group(group_id) == GroupPermissionSet(
            group_id=group_id, connector_ids=(), capabilities=(tool.as_capability(),)
        )

    def mcp_runtime_reflects_permission_changes(
        self, group_id: str, tool: ConnectorToolRef, tool_name: str
    ) -> None:
        self.permissions.save_group_permissions(
            SaveGroupPermissionsRequest(group_id=group_id, connector_ids=(), capabilities=(tool.as_capability(),))
        )
        self.runtime.reload_permissions()

        assert tool_name in self.runtime.visible_tool_names_for_jwt_groups((group_id,))

    def deleting_one_empty_group_preserves_other_groups(
        self, empty_group_id: str, permission_group_id: str, tool: ConnectorToolRef
    ) -> None:
        self.register_empty_group(empty_group_id)
        self.permissions.save_group_permissions(
            SaveGroupPermissionsRequest(
                group_id=permission_group_id, connector_ids=(), capabilities=(tool.as_capability(),)
            )
        )

        result = self.registry.deletion.delete_permission_group(empty_group_id)

        assert result.status == "applied"
        assert empty_group_id not in _visible_group_ids(self.registry.listing)
        assert self.registry.reader.get_permission_group(permission_group_id) == GroupPermissionSet(
            group_id=permission_group_id, connector_ids=(), capabilities=(tool.as_capability(),)
        )

    def deleting_local_group_does_not_manage_identity_provider_groups(self, group_id: str) -> None:
        self.register_empty_group(group_id)

        result = self.registry.deletion.delete_permission_group(group_id)

        assert result.status == "applied"
        assert group_id not in _visible_group_ids(self.registry.listing)


class FastApiPermissionGroupDriver:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def list_permission_groups(self) -> tuple[GroupPermissionSet, ...]:
        response = self.client.get("/admin/mcp-permissions/groups")
        return tuple(
            self.get_permission_group(group["group_id"]) for group in response.json()["groups"]
        )

    def get_permission_group(self, group_id: str) -> GroupPermissionSet:
        response = self.client.get(f"/admin/mcp-permissions/groups/{group_id}")
        return _group_permission_set(response.json())

    def register_permission_group(self, group_id: str) -> PermissionGroupChangeResult:
        response = self.client.post(f"/admin/mcp-permissions/groups/{group_id}")
        if response.status_code >= 400:
            return PermissionGroupChangeResult(
                status="rejected", group_id=group_id, message=response.json().get("detail")
            )
        return _permission_group_change_result(response.json())

    def delete_permission_group(self, group_id: str) -> PermissionGroupChangeResult:
        response = self.client.delete(f"/admin/mcp-permissions/groups/{group_id}")
        if response.status_code >= 400:
            return PermissionGroupChangeResult(
                status="rejected", group_id=group_id, message=response.json().get("detail")
            )
        return _permission_group_change_result(response.json())

    def save_group_permissions(
        self, request: SaveGroupPermissionsRequest
    ) -> PermissionGroupChangeResult:
        current = self.get_permission_group(request.group_id)
        desired_connectors = set(request.connector_ids)
        current_connectors = set(current.connector_ids)
        desired_capabilities = set(request.capabilities)
        current_capabilities = set(current.capabilities)
        connectors = [
            {"connector_id": connector_id, "permission_status": "enabled"}
            for connector_id in sorted(desired_connectors - current_connectors)
        ] + [
            {"connector_id": connector_id, "permission_status": "disabled"}
            for connector_id in sorted(current_connectors - desired_connectors)
        ]
        capabilities = [
            {
                "connector_id": capability.connector_id,
                "capability_kind": capability.capability_kind,
                "capability_key": capability.capability_key,
                "permission_status": "enabled",
            }
            for capability in sorted(
                desired_capabilities - current_capabilities,
                key=lambda item: (item.connector_id, item.capability_kind, item.capability_key),
            )
        ] + [
            {
                "connector_id": capability.connector_id,
                "capability_kind": capability.capability_kind,
                "capability_key": capability.capability_key,
                "permission_status": "disabled",
            }
            for capability in sorted(
                current_capabilities - desired_capabilities,
                key=lambda item: (item.connector_id, item.capability_kind, item.capability_key),
            )
        ]
        if not connectors and not capabilities:
            return PermissionGroupChangeResult(status="applied", group_id=request.group_id)
        response = self.client.put(
            f"/admin/mcp-permissions/groups/{request.group_id}/permissions",
            json={"connectors": connectors, "capabilities": capabilities},
        )
        if response.status_code >= 400:
            return PermissionGroupChangeResult(
                status="rejected", group_id=request.group_id, message=response.json().get("detail")
            )
        return _permission_group_change_result(response.json())


class FastApiPermissionGroupAuthorizationDriver:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def non_admin_can_register_permission_group(self, group_id: str) -> bool:
        return self.client.post(f"/admin/mcp-permissions/groups/{group_id}").status_code not in (
            401,
            403,
        )

    def non_admin_can_delete_permission_group(self, group_id: str) -> bool:
        return self.client.delete(f"/admin/mcp-permissions/groups/{group_id}").status_code not in (
            401,
            403,
        )


class FastApiMcpPermissionRuntimeDriver:
    def __init__(self, permissions: RuntimePermissionLookup) -> None:
        self.permissions = permissions

    def reload_permissions(self) -> None:
        return None

    def visible_tool_names_for_jwt_groups(self, group_ids: tuple[str, ...]) -> tuple[str, ...]:
        allowed_tools = []
        for group_id in group_ids:
            allowed_tools.extend(self.permissions.get_permission_group(group_id).tools)
        return tuple(sorted(f"{tool.connector_id}_{tool.operation_name}" for tool in allowed_tools))


def _visible_group_ids(registry: PermissionGroupListing) -> tuple[str, ...]:
    return tuple(group.group_id for group in registry.list_permission_groups())


@pytest.fixture
def dsl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ApplicationPermissionGroupsDsl:
    driver = _create_admin_driver(tmp_path, monkeypatch)
    return ApplicationPermissionGroupsDsl(
        registry=PermissionGroupAdminPorts(
            listing=driver, reader=driver, registration=driver, deletion=driver
        ),
        permissions=driver,
        runtime=FastApiMcpPermissionRuntimeDriver(driver),
        authorization=_create_non_admin_driver(tmp_path, monkeypatch),
    )


@pytest.mark.parametrize(
    "permission_group_scenario",
    [
        lambda dsl: dsl.register_empty_group("future-team"),
        lambda dsl: dsl.save_permission_for_new_group(
            "engineering", ConnectorToolRef("test", "echo")
        ),
        lambda dsl: dsl.delete_unused_group("future-team"),
        lambda dsl: dsl.register_existing_group_idempotently("engineering"),
        lambda dsl: dsl.register_distinct_group_values("engineering", "Engineering"),
        lambda dsl: dsl.registered_empty_group_grants_no_tools("future-team"),
    ],
    ids=[
        "register-empty-group",
        "save-registers-group-record",
        "delete-unused-group",
        "register-existing-idempotently",
        "distinct-group-values",
        "empty-group-grants-no-tools",
    ],
)
def test_admin_permission_group_scenarios(
    dsl: ApplicationPermissionGroupsDsl,
    permission_group_scenario: Callable[[ApplicationPermissionGroupsDsl], None],
) -> None:
    permission_group_scenario(dsl)


def test_deleting_a_group_with_connector_permissions_is_rejected(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    dsl.deletion_is_rejected_for_group_with_connector_permission("support", "test")


def test_deleting_a_group_with_tool_permissions_is_rejected(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    dsl.deletion_is_rejected_for_group_with_tool_permission(
        "engineering", ConnectorToolRef("test", "echo")
    )


def test_registering_an_empty_group_value_is_rejected(dsl: ApplicationPermissionGroupsDsl) -> None:
    result = dsl.registry.registration.register_permission_group("")

    assert result.status == "rejected"
    assert "" not in _visible_group_ids(dsl.registry.listing)


def test_non_admin_cannot_register_or_delete_permission_groups(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    assert dsl.authorization.non_admin_can_register_permission_group("future-team") is False
    assert dsl.authorization.non_admin_can_delete_permission_group("future-team") is False


def test_mcp_runtime_reflects_group_permission_changes_without_backend_restart(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    dsl.mcp_runtime_reflects_permission_changes(
        "engineering", ConnectorToolRef("test", "echo"), "test_echo"
    )


def test_deleting_one_empty_group_does_not_affect_other_groups(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    dsl.deleting_one_empty_group_preserves_other_groups(
        "future-team", "engineering", ConnectorToolRef("test", "echo")
    )


def test_application_layer_group_deletion_does_not_affect_identity_provider_groups(
    dsl: ApplicationPermissionGroupsDsl,
) -> None:
    dsl.deleting_local_group_does_not_manage_identity_provider_groups("future-team")


def _create_admin_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FastApiPermissionGroupDriver:
    client = _create_client(
        tmp_path,
        monkeypatch,
        APISettings(
            admin_authentication={"mode": "simulation", "simulated_admin": True},
            connector_store={
                "type": "sqlite",
                "sqlite_path": str(tmp_path / "umbod.sqlite3"),
            },
        ),
    )
    _provision_assignable_test_connector(client)
    return FastApiPermissionGroupDriver(client)


def _create_non_admin_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FastApiPermissionGroupAuthorizationDriver:
    return FastApiPermissionGroupAuthorizationDriver(
        _create_client(
            tmp_path,
            monkeypatch,
            APISettings(
                admin_authentication={
                    "mode": "jwt",
                    "jwt_header_name": "X-Forwarded-Access-Token",
                    "jwks_url": "https://identity.example.com/.well-known/jwks.json",
                    "membership_claim": "groups",
                    "required_membership": "umbod-admins",
                },
                connector_store={
                    "type": "sqlite",
                    "sqlite_path": str(tmp_path / "non-admin.sqlite3"),
                },
            ),
        )
    )


def _create_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: APISettings
) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return TestClient(
        create_app(settings=settings, connector_registrations=[TestConnectorPlugin.registration()])
    )


def _provision_assignable_test_connector(client: TestClient) -> None:
    client.put(
        "/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "test-key",
                "default_response": "Hello from test connector",
            }
        },
    )
    client.put("/admin/connectors/catalog/test/publication")
    client.put(
        "/admin/connectors/catalog/test/tools/activation",
        json={"tools": [{"tool_id": "echo", "activation_status": "enabled"}]},
    )


def _group_permission_set(value: dict[str, object]) -> GroupPermissionSet:
    return GroupPermissionSet(
        group_id=str(value["group_id"]),
        connector_ids=tuple(value["connector_ids"]),
        capabilities=tuple(
            ConnectorCapabilityRef(
                connector_id=str(capability["connector_id"]),
                capability_kind=str(capability["capability_kind"]),
                capability_key=str(capability["capability_key"]),
            )
            for capability in value["capabilities"]
        ),
    )


def _permission_group_change_result(value: dict[str, object]) -> PermissionGroupChangeResult:
    return PermissionGroupChangeResult(
        status="applied" if value["status"] == "applied" else "rejected",
        group_id=str(value["group_id"]),
        message=value.get("message"),
    )
