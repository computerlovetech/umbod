from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.groups import GroupIdentifier, GroupManagementService
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.system_settings import SettingsStorageUnavailable
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


async def get_group_management(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> GroupManagementService:
    await factories.persistence_runtime.readiness.ensure_ready()
    return create_group_management(factories.persistence_runtime.database)


async def get_active_mapping_target_ids(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> frozenset[str]:
    try:
        return await factories.group_membership_source.target_group_ids()
    except SettingsStorageUnavailable:
        raise HTTPException(status_code=503, detail="Could not check the provider group overrides.") from None


ActiveMappingTargetIds = Annotated[frozenset[str], Depends(get_active_mapping_target_ids)]


def _reject_active_mapping_target(group_id: str, target_ids: frozenset[str]) -> None:
    if group_id in target_ids:
        raise HTTPException(
            status_code=409,
            detail="Remove this group from the live provider group overrides before deleting it.",
        )


def require_deletable_group_id(group_id: str, target_ids: ActiveMappingTargetIds) -> str:
    _reject_active_mapping_target(group_id, target_ids)
    return group_id


def require_deletable_group_request(
    request: GroupIdentifier, target_ids: ActiveMappingTargetIds,
) -> GroupIdentifier:
    _reject_active_mapping_target(request.group_id, target_ids)
    return request
