from pathlib import Path

import pytest

from umbod.core.filesystem import OwnershipNotFound, StorageFailure
from umbod.core.filesystem.stores.schema import GRANT_TABLE, NODE_TABLE, OWNER_TABLE
from umbod.core.persistence import AllFields, NoFilter, Query, Unordered
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from tests.persistence_runtime import create_sqlite_runtime


@pytest.mark.asyncio
async def test_sqlite_readiness_prepares_filesystem_without_constructor_io(tmp_path: Path) -> None:
    path = tmp_path / "readiness.sqlite"
    runtime = create_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=runtime.database)
        policies = create_access_control_driver(database=runtime.database)
        assert not path.exists()
        with pytest.raises(StorageFailure):
            await namespace.get_root()
        await runtime.readiness.ensure_ready()
        async with runtime.database.read_session() as session:
            assert await session.find_many(NODE_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()
            assert await session.find_many(OWNER_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()
            assert await session.find_many(GRANT_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()
        root = await namespace.get_root()
        with pytest.raises(OwnershipNotFound):
            await policies.get_owner(root.id)
        assert tuple(await policies.list_grants(root.id)) == ()
    finally:
        await runtime.shutdown()
