from pathlib import Path

import pytest
import pytest_asyncio

from umbod.core.virtual_filesystem import (
    InMemoryContentConfig,
    InMemoryNamespaceConfig,
    LocalContentConfig,
    LocalNamespaceConfig,
)
from umbod.core.virtual_filesystem.adapters import create_content_driver, create_namespace_driver

from tests.support.virtual_filesystem import (
    FilesystemAcceptanceContext,
    create_acceptance_context,
)
from tests.support.virtual_filesystem.adapters import AdapterFactory, AdapterPair


@pytest.fixture(params=["inmemory", "local"])
def adapter_factory(request: pytest.FixtureRequest, tmp_path: Path) -> AdapterFactory:
    if request.param == "inmemory":
        shared = AdapterPair(
            create_namespace_driver(InMemoryNamespaceConfig(type="inmemory")),
            create_content_driver(InMemoryContentConfig(type="inmemory")),
        )

        def create_inmemory() -> AdapterPair:
            return shared

        return create_inmemory

    def create_local() -> AdapterPair:
        return AdapterPair(
            create_namespace_driver(LocalNamespaceConfig(type="local", directory=tmp_path / "namespace")),
            create_content_driver(LocalContentConfig(type="local", directory=tmp_path / "content")),
        )

    return create_local


@pytest.fixture
def adapters(adapter_factory: AdapterFactory) -> AdapterPair:
    return adapter_factory()


@pytest_asyncio.fixture
async def filesystem_context(adapters: AdapterPair) -> FilesystemAcceptanceContext:
    return await create_acceptance_context(adapters.namespace, adapters.content)
