from tests.persistence_runtime import create_inmemory_runtime
import pytest
from umbod.core.permissions import SaveGroupPermissionsRequest
from umbod.mcp.openapi_connectors import DatabaseGroupPermissionReaderFactory

@pytest.mark.asyncio
async def test_group_permission_readers_share_runtime_database_state() -> None:
    database = create_inmemory_runtime().database
    factory = DatabaseGroupPermissionReaderFactory(database)
    writer = await factory.create()
    reader = await factory.create()
    await writer.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=('slack',), capabilities=()))
    permissions = await reader.list_group_permissions('engineering')
    assert permissions.connector_ids == ('slack',)
