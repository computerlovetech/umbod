from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from umbod.core.administrator.connector_configuration import (
    AdministratorPrincipal,
    ConnectorDesiredState,
    ConnectorReference,
)
from umbod.core.administrator.models import PatchGroupPermissions, SearchObservedUsers
from umbod.core.administrator.operations import (
    AdministratorAccess,
    AdministratorAccessDenied,
    AdministratorChanges,
    AdministratorDiscovery,
    AdministratorInspection,
)
from umbod.core.filesystem.namespaces import (
    CreateSharedNamespace,
    SaveSharedNamespace,
    SaveSharedNamespaceDescription,
)
from umbod.core.identity_directory.models import DirectoryScope, ObservedUser, UserPage
from umbod.core.permissions.domain import (
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    GroupPermissionSet,
    PermissionChangeResult,
    PermissionStatus,
    UpdateGroupPermissionsRequest,
)


ADMIN = AdministratorPrincipal(memberships=("ops",))
pytestmark = pytest.mark.asyncio


async def test_search_users_projects_profiles_without_raw_identity_fields() -> None:
    now = datetime.now(UTC)
    users = AsyncMock()
    users.search_users.return_value = UserPage(
        issuer="https://issuer.example",
        users=(
            ObservedUser(
                user_id="opaque-id",
                issuer="https://issuer.example",
                subject="raw-subject",
                name="Taylor",
                email="taylor@example.com",
                email_verification="verified",
                first_seen_at=now,
                last_seen_at=now,
            ),
        ),
        has_more=True,
    )
    discovery = AdministratorDiscovery(
        AdministratorAccess("ops"),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        users,
        AsyncMock(),
        issuer="https://issuer.example",
        permission_group_claim="groups",
    )

    result = await discovery.search_users(ADMIN, SearchObservedUsers(query=" Taylor "))

    users.search_users.assert_awaited_once_with(
        DirectoryScope(
            issuer="https://issuer.example",
            claim="groups",
            query="Taylor",
            limit=20,
            user_search_fields="profile",
        )
    )
    assert result.model_dump() == {
        "users": (
            {
                "user_id": "opaque-id",
                "name": "Taylor",
                "email": "taylor@example.com",
                "last_seen_at": now,
            },
        ),
        "has_more": True,
    }


async def test_non_admin_cannot_trigger_discovery_or_mutation() -> None:
    backend = AsyncMock()
    denied = AdministratorPrincipal(memberships=("Ops",))
    access = AdministratorAccess("ops")
    discovery = AdministratorDiscovery(
        access,
        backend,
        backend,
        backend,
        backend,
        backend,
        issuer="https://issuer.example",
        permission_group_claim="groups",
    )
    changes = AdministratorChanges(access, backend, backend, backend)
    patch = PatchGroupPermissions(
        group_id="Team",
        connectors=(ConnectorPermissionUpdate("connector", "disabled"),),
    )

    inspection = AdministratorInspection(access, backend, backend)
    connector = ConnectorReference(connector_kind="native", connector_id="connector")
    operations = (
        discovery.list_connectors(denied),
        discovery.list_groups(denied),
        discovery.list_permission_targets(denied),
        discovery.search_users(denied, SearchObservedUsers(query="Taylor")),
        discovery.list_namespaces(denied),
        inspection.read_connector_configuration(denied, connector),
        inspection.read_group_permissions(denied, "Team"),
        changes.update_connector_configuration(
            denied, connector, ConnectorDesiredState()
        ),
        changes.update_group_permissions(denied, patch),
        changes.create_namespace(
            denied, CreateSharedNamespace(name="Shared", groups=[])
        ),
        changes.update_namespace(
            denied,
            UUID(int=1),
            SaveSharedNamespace(name="Shared", groups=[], expected_revision=1),
        ),
    )
    for operation in operations:
        with pytest.raises(AdministratorAccessDenied):
            await operation

    assert backend.mock_calls == []


async def test_group_inspection_preserves_stale_direct_grants() -> None:
    permissions = AsyncMock()
    grants = GroupPermissionSet(
        "Team ", (), (ConnectorCapabilityRef("removed", "tool", "oldTool"),)
    )
    permissions.list_group_permissions.return_value = grants
    inspection = AdministratorInspection(
        AdministratorAccess("ops"), AsyncMock(), permissions
    )

    assert await inspection.read_group_permissions(ADMIN, "Team ") == grants
    permissions.list_group_permissions.assert_awaited_once_with("Team ")


async def test_group_patch_preserves_exact_target_and_delegates_stale_revocation() -> (
    None
):
    permissions = AsyncMock()
    permissions.update_group_permissions.return_value = PermissionChangeResult(
        "applied", "Team "
    )
    changes = AdministratorChanges(
        AdministratorAccess("ops"), AsyncMock(), permissions, AsyncMock()
    )
    revocation = ConnectorPermissionUpdate("removed", "disabled")

    result = await changes.update_group_permissions(
        ADMIN, PatchGroupPermissions(group_id="Team ", connectors=(revocation,))
    )

    assert result.status == "applied"
    permissions.update_group_permissions.assert_awaited_once_with(
        UpdateGroupPermissionsRequest("Team ", (revocation,), ())
    )


@pytest.mark.parametrize(
    "targets",
    [
        (),
        (
            ConnectorPermissionUpdate("same", "enabled"),
            ConnectorPermissionUpdate("same", "disabled"),
        ),
    ],
)
async def test_group_patch_rejects_empty_or_duplicate_targets(
    targets: tuple[ConnectorPermissionUpdate, ...],
) -> None:
    with pytest.raises(ValidationError):
        PatchGroupPermissions(group_id="Team", connectors=targets)


async def test_group_patch_rejects_invalid_status_on_existing_dataclass() -> None:
    target = ConnectorPermissionUpdate("connector", cast(PermissionStatus, "invalid"))

    with pytest.raises(ValidationError, match="Permission status"):
        PatchGroupPermissions(group_id="Team", connectors=(target,))


async def test_namespace_replacement_preserves_both_revisions_and_empty_assignments() -> (
    None
):
    namespace_id = UUID(int=1)
    namespaces = AsyncMock()
    changes = AdministratorChanges(
        AdministratorAccess("ops"), AsyncMock(), AsyncMock(), namespaces
    )
    command = SaveSharedNamespaceDescription(
        name="Shared",
        groups=[],
        description="",
        expected_revision=2,
        expected_root_revision=5,
    )

    await changes.update_namespace(ADMIN, namespace_id, command)

    namespaces.save.assert_awaited_once_with(namespace_id, command)
