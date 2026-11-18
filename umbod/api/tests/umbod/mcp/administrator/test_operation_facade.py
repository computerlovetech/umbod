from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from pydantic import TypeAdapter, ValidationError

from umbod.core.administrator import AdministratorAccessDenied, ObservedUserMatches
from umbod.core.administrator.connector_configuration import (
    AdministratorPrincipal,
    ConfigurationError,
    ConfigurationRejected,
)
from umbod.core.filesystem.errors import PolicyRevisionConflict
from umbod.core.permissions.domain import GroupPermissionSet, PermissionChangeResult
from umbod.mcp.administrator import operation_facade as facade_module
from umbod.mcp.administrator.operation_facade import AdministratorOperationFacade
from umbod.mcp.administrator.operation_inputs import (
    ApplyOperation,
    DiscoverOperation,
    InspectOperation,
)
from umbod.mcp.responses.progress import operation_progress_context
from umbod.mcp.tools.errors import BuiltinToolAuthorizationDenied, BuiltinToolRejected


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> AdministratorPrincipal:
    principal = AdministratorPrincipal(memberships=("admin",))

    def capture(claim: str) -> AdministratorPrincipal:
        assert claim == "admin_membership"
        return principal

    monkeypatch.setattr(facade_module, "current_administrator_principal", capture)
    return principal


@pytest.mark.asyncio
async def test_facade_schema_and_result_round_trip(
    principal: AdministratorPrincipal,
) -> None:
    inspection = AsyncMock()
    inspection.read_group_permissions.return_value = GroupPermissionSet(
        " Team ", ("removed",), ()
    )
    facade = AdministratorOperationFacade(
        AsyncMock(), inspection, AsyncMock(), "admin_membership"
    )
    mcp = FastMCP("facade test")
    mcp.add_tool(facade.admin_inspect)

    async with Client(mcp) as client:
        (descriptor,) = await client.list_tools()
        request_schema = descriptor.input_schema["properties"]["request"]
        branches = request_schema.get("oneOf", request_schema.get("anyOf", []))
        assert {branch["properties"]["operation"]["const"] for branch in branches} == {
            "read_connector_configuration",
            "read_group_permissions",
        }
        result = await client.call_tool(
            "admin_inspect",
            {
                "request": {
                    "operation": "read_group_permissions",
                    "group_id": " Team ",
                },
            },
        )

    inspection.read_group_permissions.assert_awaited_once_with(principal, " Team ")
    assert result.structured_content["result"] == {
        "operation": "read_group_permissions",
        "result": {
            "group_id": " Team ",
            "connector_ids": ["removed"],
            "capabilities": [],
        },
    }


@pytest.mark.asyncio
async def test_discover_dispatches_validated_search_and_marks_completion(
    principal: AdministratorPrincipal,
) -> None:
    discovery = AsyncMock()
    discovery.search_users.return_value = ObservedUserMatches(users=(), has_more=False)
    facade = AdministratorOperationFacade(
        discovery, AsyncMock(), AsyncMock(), "admin_membership"
    )
    request = TypeAdapter(DiscoverOperation).validate_python(
        {"operation": "search_users", "query": "  Taylor  ", "limit": 3}
    )

    with operation_progress_context() as progress:
        response = await facade.admin_discover(request)

    discovery.search_users.assert_awaited_once_with(principal, request)
    assert request.query == "Taylor"
    assert response.model_dump() == {
        "operation": "search_users",
        "result": {"users": (), "has_more": False},
    }
    assert progress.state.value == "completed"


def test_discovery_does_not_accept_caller_claims() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(DiscoverOperation).validate_python(
            {
                "operation": "list_groups",
                "memberships": ["admin"],
            }
        )


def test_namespace_description_requires_root_revision() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ApplyOperation).validate_python(
            {
                "operation": "update_namespace",
                "namespace_id": "00000000-0000-0000-0000-000000000001",
                "namespace": {
                    "name": "Shared",
                    "groups": [],
                    "expected_revision": 2,
                    "description": "",
                },
            }
        )


@pytest.mark.asyncio
async def test_apply_group_patch_uses_safe_rejection(
    principal: AdministratorPrincipal,
) -> None:
    changes = AsyncMock()
    changes.update_group_permissions.return_value = PermissionChangeResult(
        "rejected", "ops", "internal detail"
    )
    facade = AdministratorOperationFacade(
        AsyncMock(), AsyncMock(), changes, "admin_membership"
    )
    patch = TypeAdapter(ApplyOperation).validate_python(
        {
            "operation": "update_group_permissions",
            "group_id": "ops",
            "connectors": [
                {"connector_id": "removed", "permission_status": "disabled"}
            ],
        }
    )

    with pytest.raises(BuiltinToolRejected) as error:
        await facade.admin_apply(patch)

    changes.update_group_permissions.assert_awaited_once_with(principal, patch)
    assert error.value.details.code == "group_permission_update_rejected"
    assert "internal detail" not in str(error.value)


@pytest.mark.asyncio
async def test_namespace_conflict_provides_safe_recovery(
    principal: AdministratorPrincipal,
) -> None:
    changes = AsyncMock()
    changes.update_namespace.side_effect = PolicyRevisionConflict(
        "internal revision detail"
    )
    facade = AdministratorOperationFacade(
        AsyncMock(), AsyncMock(), changes, "admin_membership"
    )
    command = TypeAdapter(ApplyOperation).validate_python(
        {
            "operation": "update_namespace",
            "namespace_id": "00000000-0000-0000-0000-000000000001",
            "namespace": {"name": "Shared", "groups": [], "expected_revision": 2},
        }
    )

    with (
        operation_progress_context() as progress,
        pytest.raises(BuiltinToolRejected) as error,
    ):
        await facade.admin_apply(command)

    changes.update_namespace.assert_awaited_once_with(
        principal, command.namespace_id, command.namespace
    )
    assert progress.state.value == "unknown"
    assert error.value.details.code == "namespace_revision_conflict"
    assert "internal revision detail" not in str(error.value)


@pytest.mark.asyncio
async def test_core_denial_does_not_escape_as_an_internal_error(
    principal: AdministratorPrincipal,
) -> None:
    inspection = AsyncMock()
    inspection.read_group_permissions.side_effect = AdministratorAccessDenied()
    facade = AdministratorOperationFacade(
        AsyncMock(), inspection, AsyncMock(), "admin_membership"
    )
    request = TypeAdapter(InspectOperation).validate_python(
        {
            "operation": "read_group_permissions",
            "group_id": "ops",
        }
    )

    with (
        operation_progress_context() as progress,
        pytest.raises(BuiltinToolAuthorizationDenied) as error,
    ):
        await facade.admin_inspect(request)

    assert progress.state.value == "not_started"

    inspection.read_group_permissions.assert_awaited_once_with(principal, "ops")
    assert error.value.details.code == "administrator_access_denied"
    assert error.value.retry.value == "after_permission_change"


@pytest.mark.asyncio
@pytest.mark.parametrize("is_write", [False, True])
async def test_connector_rejection_references_nested_input(
    principal: AdministratorPrincipal,
    is_write: bool,
) -> None:
    service = AsyncMock()
    rejection = ConfigurationRejected(
        error=ConfigurationError(
            code="connector_not_found",
            message="internal detail",
        )
    )
    service.read_connector_configuration.return_value = rejection
    service.update_connector_configuration.return_value = rejection
    facade = AdministratorOperationFacade(
        AsyncMock(), service, service, "admin_membership"
    )
    connector = {"connector_kind": "native", "connector_id": "missing"}

    with pytest.raises(BuiltinToolRejected) as error:
        if is_write:
            await facade.admin_apply(
                TypeAdapter(ApplyOperation).validate_python(
                    {
                        "operation": "update_connector_configuration",
                        "connector": connector,
                        "desired_state": {"operations": []},
                    }
                )
            )
        else:
            await facade.admin_inspect(
                TypeAdapter(InspectOperation).validate_python(
                    {
                        "operation": "read_connector_configuration",
                        "connector": connector,
                    }
                )
            )

    assert error.value.details.issues[0].field == "request.connector.connector_id"
    assert "internal detail" not in str(error.value)
