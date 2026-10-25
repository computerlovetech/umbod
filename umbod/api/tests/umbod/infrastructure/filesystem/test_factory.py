from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    NodeKind,
    NodeMetadata,
    StorageFailure,
    UnspecifiedContentType,
)
from umbod.infrastructure import (
    InMemoryContentConfig,
    InMemoryNamespaceConfig,
    LocalContentConfig,
    LocalNamespaceConfig,
    FilesystemConfig,
    create_content_driver,
    create_namespace_driver,
    create_filesystem,
)

from tests.support.filesystem.protocols import PublicFilesystem

Backend = Literal["inmemory", "local"]


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


def configuration(
    namespace_type: Backend, content_type: Backend, directory: Path,
) -> FilesystemConfig:
    namespace = (
        LocalNamespaceConfig(type="local", directory=directory / "namespace")
        if namespace_type == "local" else InMemoryNamespaceConfig(type="inmemory")
    )
    content = (
        LocalContentConfig(type="local", directory=directory / "content")
        if content_type == "local" else InMemoryContentConfig(type="inmemory")
    )
    return FilesystemConfig(namespace=namespace, content=content)


@pytest.mark.asyncio
@pytest.mark.parametrize("namespace_type", ["inmemory", "local"])
@pytest.mark.parametrize("content_type", ["inmemory", "local"])
async def test_configured_factory_composes_a_working_service(
    namespace_type: Backend, content_type: Backend, tmp_path: Path,
) -> None:
    config = configuration(namespace_type, content_type, tmp_path)
    filesystem: PublicFilesystem = create_filesystem(config)
    root = await filesystem.get_root()
    file = await filesystem.create_file(
        root.id, "payload", NodeMetadata(content_type="application/octet-stream", attributes={}),
    )
    written = await filesystem.write(file.id, stream(b"configured\x00bytes"), expected_revision=file.revision)

    assert await filesystem.get_node(file.id) == written
    assert b"".join([chunk async for chunk in filesystem.read(file.id)]) == b"configured\x00bytes"
    assert tuple(await filesystem.list_children(root.id)) == (written,)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["inmemory", "local"])
async def test_namespace_factory_honors_backend_persistence(backend: Backend, tmp_path: Path) -> None:
    config = configuration(backend, "inmemory", tmp_path)
    first = create_namespace_driver(config.namespace)
    root = await first.get_root()
    node = await first.create_node(
        root.id, "retained", NodeKind.FILE,
        NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
    )
    second = create_namespace_driver(config.namespace)

    children = tuple(await second.list_children(root.id))
    assert children == ((node,) if backend == "local" else ())


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["inmemory", "local"])
async def test_content_factory_honors_backend_persistence(backend: Backend, tmp_path: Path) -> None:
    config = configuration("inmemory", backend, tmp_path)
    first = create_content_driver(config.content)
    reference = await first.put(stream(b"stored bytes"))
    second = create_content_driver(config.content)

    if backend == "local":
        assert b"".join([chunk async for chunk in second.get(reference.key)]) == b"stored bytes"
    else:
        with pytest.raises(StorageFailure):
            async for _ in second.get(reference.key):
                pytest.fail("A fresh in-memory content adapter must not retain another instance's data")


@pytest.mark.asyncio
async def test_final_service_factory_reopens_configured_local_storage(tmp_path: Path) -> None:
    config = configuration("local", "local", tmp_path)
    first: PublicFilesystem = create_filesystem(config)
    root = await first.get_root()
    file = await first.create_file(
        root.id, "persisted", NodeMetadata(content_type="text/plain", attributes={}),
    )
    written = await first.write(file.id, stream(b"persistent"), expected_revision=file.revision)
    reopened: PublicFilesystem = create_filesystem(config)

    assert await reopened.get_root() == root
    assert await reopened.get_node(file.id) == written
    assert b"".join([chunk async for chunk in reopened.read(file.id)]) == b"persistent"


@pytest.mark.parametrize("configuration_value", [
    {},
    {"namespace": {"type": "inmemory"}},
    {"namespace": {"type": "unsupported"}, "content": {"type": "inmemory"}},
    {"namespace": {"type": "inmemory"}, "content": {"type": "unsupported"}},
    {"namespace": {"type": "local"}, "content": {"type": "inmemory"}},
    {"namespace": {"type": "inmemory"}, "content": {"type": "local"}},
    {"namespace": {"type": "local", "directory": ""}, "content": {"type": "inmemory"}},
    {"namespace": {"type": "inmemory"}, "content": {"type": "local", "directory": " "}},
    {"namespace": {"type": "inmemory", "directory": "/unused"}, "content": {"type": "inmemory"}},
    {"namespace": {"type": "inmemory"}, "content": {"type": "inmemory", "directory": "/unused"}},
    {"namespace": {"type": "inmemory"}, "content": {"type": "inmemory"}, "unknown": True},
])
def test_invalid_adapter_configuration_is_rejected(configuration_value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FilesystemConfig.model_validate(configuration_value)


def test_serialized_configuration_declares_independent_adapter_types(tmp_path: Path) -> None:
    value = {
        "namespace": {"type": "local", "directory": str(tmp_path / "namespace")},
        "content": {"type": "inmemory"},
    }
    config = FilesystemConfig.model_validate(value)

    assert config.namespace.type == "local"
    assert config.namespace.directory == tmp_path / "namespace"
    assert config.content.type == "inmemory"
    assert FilesystemConfig.model_validate_json(config.model_dump_json()) == config
