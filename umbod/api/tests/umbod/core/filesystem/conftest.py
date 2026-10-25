from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    InMemoryContentConfig,
    LocalContentConfig,
    create_content_driver,
    create_namespace_driver,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.support.filesystem import (
    FilesystemAcceptanceContext,
    create_acceptance_context,
)
from tests.support.filesystem.adapters import AdapterFactory, AdapterPair


@pytest_asyncio.fixture(params=["inmemory", "sqlite"])
async def filesystem_runtime(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[PersistenceRuntime]:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "filesystem.db")
    )
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@pytest.fixture(params=["inmemory", "local"])
def adapter_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    filesystem_runtime: PersistenceRuntime,
) -> AdapterFactory:
    content = (
        create_content_driver(InMemoryContentConfig(type="inmemory"))
        if request.param == "inmemory"
        else create_content_driver(
            LocalContentConfig(type="local", directory=tmp_path / "content")
        )
    )

    def create() -> AdapterPair:
        return AdapterPair(
            create_namespace_driver(database=filesystem_runtime.database), content
        )

    return create


@pytest.fixture
def adapters(adapter_factory: AdapterFactory) -> AdapterPair:
    return adapter_factory()


@pytest_asyncio.fixture
async def filesystem_context(adapters: AdapterPair) -> FilesystemAcceptanceContext:
    return await create_acceptance_context(adapters.namespace, adapters.content)
