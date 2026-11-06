import asyncio

import pytest

from umbod.core.filesystem import Permission
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.infrastructure import create_filesystem_sharing
from tests.umbod.core.filesystem.test_authorized_content import caller
from .conftest import SharingContext
from .test_user_policy import observe, user_command


@pytest.mark.asyncio
async def test_independent_services_union_concurrent_user_permissions(context: SharingContext) -> None:
    user_id = await observe(DatabaseIdentityDirectory(context.database), "issuer", "recipient")
    other = create_filesystem_sharing(database=context.database, resolver=VerifiedIdentityResolver(), issuer="issuer")
    requests = tuple(Permission)
    results = await asyncio.wait_for(asyncio.gather(*(
        (context.service if index % 2 else other).share(
            caller(), context.node.id, user_command(user_id, permission),
        ) for index, permission in enumerate(requests)
    )), 5)
    assert all(result.changed for result in results)
    summary = (await context.service.summarize_nodes(caller(), (context.node.id,))).nodes[0]
    assert summary.can_share and summary.grants[0].permissions == frozenset(Permission)
