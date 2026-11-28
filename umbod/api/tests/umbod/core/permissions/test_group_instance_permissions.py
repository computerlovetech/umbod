import pytest

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.reads import DatabaseGroupInstanceLookup
from umbod.core.permissions import (
    ConnectorCapabilityRef,
    GroupPermissionSet,
    SaveGroupPermissionsRequest,
)
from umbod.core.permissions.factories import (
    create_group_instance_permission_reader,
    create_group_permission_store,
)


@pytest.mark.asyncio
async def test_instance_reader_does_not_follow_permissions_to_a_replacement_group() -> (
    None
):
    runtime = await prepared_inmemory_runtime()
    group_id = "build-agent"
    register = RegisterGroup(group_id=group_id)
    try:
        groups = create_group_management(runtime.database)
        lookup = DatabaseGroupInstanceLookup(runtime.database)
        store = await create_group_permission_store(runtime.database)
        reader = create_group_instance_permission_reader(runtime.database)
        await groups.register_group(register)
        original = await lookup.find_group_instance(group_id)
        assert original is not None
        await groups.delete_group(group_id)
        await groups.register_group(register)
        replacement = await lookup.find_group_instance(group_id)
        assert replacement is not None
        operation = ConnectorCapabilityRef(
            connector_id="workspace", capability_kind="tool", capability_key="build"
        )
        await store.save_group_permissions(
            SaveGroupPermissionsRequest(
                group_id=group_id,
                connector_ids=("workspace",),
                capabilities=(operation,),
            )
        )

        assert await reader.read_for_group_instance(original) == GroupPermissionSet(
            group_id="", connector_ids=(), capabilities=()
        )
        assert await reader.read_for_group_instance(replacement) == GroupPermissionSet(
            group_id=group_id, connector_ids=("workspace",), capabilities=(operation,)
        )
    finally:
        await runtime.shutdown()
