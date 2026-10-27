from collections import Counter

import pytest

from tests.umbod.rest.mcp_permissions.assignable_support import (
    AdminPermissionHttp,
    assert_shared_targets,
    read_assignable_targets,
)
from tests.umbod.rest.user_catalogue.test_catalogue_query_budget import seed_shared_tools
from umbod.core.activation import ActivationStatus, CapabilityActivationState, CapabilityRef
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE
from umbod.core.connectors.openapi.stores.schema import CONNECTOR_TABLE
from umbod.core.permissions import AssignablePermissionCatalog
from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE, CONNECTOR_PERMISSION_TABLE
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.rest.factories import ConnectorApiDependencyFactories


@pytest.mark.parametrize("tool_count", [1, 40, 100])
def test_assignable_targets_read_and_session_budgets_do_not_grow_with_shared_tool_count(
    admin_permission_http: AdminPermissionHttp, tool_count: int,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, tool_count)

    targets = read_assignable_targets(client, counts)

    assert_shared_targets(targets, {f"read_{index}" for index in range(tool_count)})
    assert counts.reads == Counter({
        CONNECTOR_TABLE.name: 1,
        CONNECTOR_DEFINITION_TABLE.name: 1,
        TOOL_CATALOG_TABLE.name: 1,
        PUBLICATION_STATE_TABLE.name: 1,
        CAPABILITY_ACTIVATION_STATE_TABLE.name: 1,
    })
    assert counts.sessions == 4


async def set_shared_publication(
    factories: ConnectorApiDependencyFactories, published: bool,
) -> None:
    store = await factories.connector_publishing_store.create()
    if published:
        await store.publish_connector("shared")
    else:
        await store.unpublish_connector("shared")


async def disable_shared_tool(factories: ConnectorApiDependencyFactories) -> None:
    store = await factories.capability_activation_store.create()
    await store.set_statuses((CapabilityActivationState(
        ref=CapabilityRef(
            connector_kind="downstream_mcp", connector_id="shared",
            capability_kind="tool", capability_key="read_0",
        ),
        activation_status=ActivationStatus.DISABLED,
    ),))


def test_assignable_targets_observe_publication_withdrawal_and_restoration_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(set_shared_publication, factories, False)
    assert_shared_targets(read_assignable_targets(client, counts), set())

    client.portal.call(set_shared_publication, factories, True)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})


def test_assignable_targets_observe_disabled_activation_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(disable_shared_tool, factories)

    assert_shared_targets(read_assignable_targets(client, counts), {"read_1"})


def test_assignable_targets_observe_replaced_catalogue_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(seed_shared_tools, factories, 1)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0"})

    client.portal.call(seed_shared_tools, factories, 3)
    assert_shared_targets(
        read_assignable_targets(client, counts), {"read_0", "read_1", "read_2"},
    )


def test_permission_mutation_does_not_use_assignable_targets_cached_provider(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    from umbod.rest.mcp_permissions.assignable_reads import (
        get_assignable_read_state,
        get_prepared_assignable_catalogs,
    )
    from umbod.rest.mcp_permissions.dependencies import get_assignable_permission_catalog

    client, app, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    def reject_cached_catalog() -> AssignablePermissionCatalog:
        raise AssertionError("Permission mutations must not use the assignable GET catalog")

    def reject_prepared_reads() -> None:
        raise AssertionError("Group detail and mutations must not prepare assignable reads")

    app.dependency_overrides[get_assignable_permission_catalog] = reject_cached_catalog
    app.dependency_overrides[get_prepared_assignable_catalogs] = reject_prepared_reads
    app.dependency_overrides[get_assignable_read_state] = reject_prepared_reads
    response = client.put("/api/admin/mcp-permissions/groups/readers/permissions", json={
        "connectors": [],
        "capabilities": [{
            "connector_id": "shared", "capability_kind": "tool",
            "capability_key": "read_0", "permission_status": "disabled",
        }],
    })
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "applied", "group_id": "readers"}

    counts.reset()
    group = client.get("/api/admin/mcp-permissions/groups/readers")
    assert group.status_code == 200, group.text
    assert counts.reads == Counter({
        CONNECTOR_PERMISSION_TABLE.name: 1,
        CAPABILITY_PERMISSION_TABLE.name: 1,
    })
    assert counts.sessions == 1
    assert not counts.writes
    assert counts.schema_calls == 0
    assert group.json() == {
        "group_id": "readers", "connector_ids": [],
        "capabilities": [{
            "connector_id": "shared", "capability_kind": "tool", "capability_key": "read_1",
        }],
    }
