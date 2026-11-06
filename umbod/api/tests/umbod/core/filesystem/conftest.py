from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio

from umbod.core.filesystem import NamespaceDriver
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    InMemoryContentConfig,
    LocalContentConfig,
    create_content_driver,
    create_namespace_driver,
)
from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.filesystem import (
    FilesystemAcceptanceContext,
    create_acceptance_context,
)
from tests.support.filesystem.adapters import AdapterFactory, AdapterPair


@pytest_asyncio.fixture
async def filesystem_runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@pytest.fixture
def namespace_factory(
    filesystem_runtime: PersistenceRuntime,
) -> Callable[[], NamespaceDriver]:
    def create() -> NamespaceDriver:
        return create_namespace_driver(database=filesystem_runtime.database)

    return create


@pytest.fixture
def namespace(namespace_factory: Callable[[], NamespaceDriver]) -> NamespaceDriver:
    return namespace_factory()


@pytest.fixture(params=["inmemory", "local"])
def adapter_factory(
    request: pytest.FixtureRequest,
    namespace_factory: Callable[[], NamespaceDriver],
) -> AdapterFactory:
    content = (
        create_content_driver(InMemoryContentConfig(type="inmemory"))
        if request.param == "inmemory"
        else create_content_driver(
            LocalContentConfig(
                type="local", directory=request.getfixturevalue("tmp_path") / "content"
            )
        )
    )

    def create() -> AdapterPair:
        return AdapterPair(namespace_factory(), content)

    return create


@pytest.fixture
def adapters(adapter_factory: AdapterFactory) -> AdapterPair:
    return adapter_factory()


@pytest_asyncio.fixture
async def filesystem_context(adapters: AdapterPair) -> FilesystemAcceptanceContext:
    return await create_acceptance_context(adapters.namespace, adapters.content)
