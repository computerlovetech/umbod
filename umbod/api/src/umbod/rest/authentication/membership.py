from typing import Annotated

from fastapi import Depends

from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.callers.membership import GroupMembershipResolver, INHERITED_GROUP_MEMBERSHIP
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .deps import get_caller_context


async def get_group_membership_resolver(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> GroupMembershipResolver:
    if caller.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED:
        return INHERITED_GROUP_MEMBERSHIP
    return await factories.group_membership_source.capture()


RequestGroupMembershipResolver = Annotated[GroupMembershipResolver, Depends(get_group_membership_resolver)]
