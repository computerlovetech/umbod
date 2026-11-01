from tests.support.filesystem.sharing_policy import GROUP_SCOPE
import pytest

from umbod.core.filesystem import NodeKind, Ownership, Permission
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.content import ContentService
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.infrastructure import (
    InMemoryContentConfig, create_content_driver, create_filesystem_transactions,
)
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata, stream
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext
from .test_user_policy import observe, user_command


@pytest.mark.asyncio
async def test_recipient_can_read_after_user_share_with_exact_issuer(context: SharingContext) -> None:
    content = ContentService(
        VerifiedIdentityResolver(), create_filesystem_transactions(database=context.database),
        create_content_driver(InMemoryContentConfig(type="inmemory")), 1024,
    )
    file = await content.upload(caller(), context.node.id, "private", metadata(), stream(b"private bytes"))
    original = await context.namespace.get_node(file.id)
    user_id = await observe(DatabaseIdentityDirectory(context.database), "issuer", "recipient")
    actor = snapshot("recipient", "issuer", ())
    foreign = snapshot("recipient", "foreign", ())
    with pytest.raises(PermissionDenied):
        await content.open_download(actor, file.id)
    await context.service.share(caller(), file.id, user_command(user_id, Permission.DISCOVER, Permission.READ))
    download = await content.open_download(actor, file.id)
    assert b"".join([chunk async for chunk in download.data]) == b"private bytes"
    with pytest.raises(PermissionDenied):
        await content.open_download(foreign, file.id)
    assert await context.namespace.get_node(file.id) == original


@pytest.mark.asyncio
async def test_user_directory_sharing_is_not_inherited_and_adds_no_implicit_permissions(context: SharingContext) -> None:
    child = await context.namespace.create_node(context.node.id, "child", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=child.id, owner=alice()))
    user_id = await observe(DatabaseIdentityDirectory(context.database), "issuer", "recipient")
    await context.service.share(caller(), context.node.id, user_command(user_id, Permission.SHARE))
    actor = snapshot("recipient", "issuer", ())
    for node_id in (context.node.id, child.id):
        with pytest.raises(PermissionDenied):
            await context.service.inspect(actor, node_id, GROUP_SCOPE)
    await context.service.share(caller(), context.node.id, user_command(user_id, Permission.DISCOVER))
    assert (await context.service.summarize_nodes(actor, (context.node.id,))).nodes[0].can_share
    with pytest.raises(PermissionDenied):
        await context.service.inspect(actor, child.id, GROUP_SCOPE)
