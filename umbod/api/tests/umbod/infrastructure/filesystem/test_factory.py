from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

import pytest
import pytest_asyncio
from pydantic import ValidationError

from umbod.core.filesystem import NodeMetadata, StorageFailure
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    InMemoryContentConfig,
    LocalContentConfig,
    FilesystemConfig,
    create_content_driver,
    create_filesystem,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.support.filesystem.protocols import PublicFilesystem

Backend = Literal["inmemory", "local"]


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest_asyncio.fixture(params=["inmemory", "sqlite"])
async def runtime(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[PersistenceRuntime]:
    instance = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "factory.db")
    )
    try:
        yield instance
    finally:
        await instance.shutdown()


def configuration(content_type: Backend, directory: Path) -> FilesystemConfig:
    content = (
        LocalContentConfig(type="local", directory=directory / "content")
        if content_type == "local"
        else InMemoryContentConfig(type="inmemory")
    )
    return FilesystemConfig(content=content)


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["inmemory", "local"])
async def test_configured_factory_composes_a_working_service(
    content_type: Backend, tmp_path: Path, runtime: PersistenceRuntime
) -> None:
    config = configuration(content_type, tmp_path)
    filesystem: PublicFilesystem = create_filesystem(config, database=runtime.database)
    root = await filesystem.get_root()
    file = await filesystem.create_file(
        root.id,
        "payload",
        NodeMetadata(content_type="application/octet-stream", attributes={}),
    )
    written = await filesystem.write(
        file.id, stream(b"configured\x00bytes"), expected_revision=file.revision
    )
    assert await filesystem.get_node(file.id) == written
    assert (
        b"".join([chunk async for chunk in filesystem.read(file.id)])
        == b"configured\x00bytes"
    )
    assert tuple(await filesystem.list_children(root.id)) == (written,)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["inmemory", "local"])
async def test_content_factory_honors_backend_persistence(
    backend: Backend, tmp_path: Path
) -> None:
    config = configuration(backend, tmp_path)
    first = create_content_driver(config.content)
    reference = await first.put(stream(b"stored bytes"))
    second = create_content_driver(config.content)
    if backend == "local":
        assert (
            b"".join([chunk async for chunk in second.get(reference.key)])
            == b"stored bytes"
        )
    else:
        with pytest.raises(StorageFailure):
            async for _ in second.get(reference.key):
                pytest.fail(
                    "A fresh in-memory content adapter must not retain another instance's data"
                )


@pytest.mark.parametrize(
    "configuration_value",
    [
        {},
        {"content": {"type": "unsupported"}},
        {"content": {"type": "local"}},
        {"content": {"type": "local", "directory": ""}},
        {"content": {"type": "local", "directory": " "}},
        {"content": {"type": "inmemory", "directory": "/unused"}},
        {"content": {"type": "inmemory"}, "unknown": True},
        {"content": {"type": "inmemory"}, "namespace": {"type": "inmemory"}},
        {
            "content": {"type": "inmemory"},
            "namespace": {"type": "local", "directory": "/unused"},
        },
    ],
)
def test_invalid_adapter_configuration_is_rejected(
    configuration_value: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FilesystemConfig.model_validate(configuration_value)


def test_serialized_configuration_declares_content_only() -> None:
    value = {"content": {"type": "inmemory"}}
    config = FilesystemConfig.model_validate(value)
    assert config.model_dump(mode="json") == value
    assert FilesystemConfig.model_validate_json(config.model_dump_json()) == config
