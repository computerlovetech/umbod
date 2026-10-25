import asyncio
import fcntl
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from collections.abc import AsyncIterator
from pathlib import Path
from threading import Event

import pytest

from umbod.core.filesystem import (
    ContentDriver,
    NamespaceDriver,
    NodeKind,
    NodeMetadata,
    StorageFailure,
    UnspecifiedContentType,
    Filesystem,
)
from umbod.infrastructure.filesystem.local_content import LocalContent
from umbod.infrastructure.filesystem.local_namespace import LocalNamespace

from tests.support.filesystem.processes import create_local_child_in_process


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.asyncio
async def test_reopened_adapters_preserve_root_hierarchy_metadata_and_bytes(tmp_path: Path) -> None:
    namespace_directory = tmp_path / "namespace"
    content_directory = tmp_path / "content"
    original = Filesystem(
        namespace=LocalNamespace(namespace_directory), content=LocalContent(content_directory),
    )
    root = await original.get_root()
    directory = await original.create_directory(
        root.id, "Reports", NodeMetadata(content_type=UnspecifiedContentType(), attributes={"team": "one"}),
    )
    file = await original.create_file(
        directory.id, "Résumé.txt", NodeMetadata(content_type="text/plain", attributes={"language": "fr"}),
    )
    written = await original.write(file.id, stream(b"persisted\x00bytes"), expected_revision=file.revision)
    reopened = Filesystem(
        namespace=LocalNamespace(namespace_directory), content=LocalContent(content_directory),
    )

    assert await reopened.get_root() == root
    assert tuple(await reopened.list_children(root.id)) == (directory,)
    assert await reopened.get_node(file.id) == written
    assert b"".join([chunk async for chunk in reopened.read(file.id)]) == b"persisted\x00bytes"


@pytest.mark.asyncio
async def test_corrupt_namespace_is_not_silently_replaced(tmp_path: Path) -> None:
    namespace: NamespaceDriver = LocalNamespace(tmp_path)
    await namespace.get_root()
    snapshot = tmp_path / "namespace.json"
    snapshot.write_bytes(b"not valid json")
    reopened: NamespaceDriver = LocalNamespace(tmp_path)

    with pytest.raises(StorageFailure):
        await reopened.get_root()

    assert snapshot.read_bytes() == b"not valid json"


@pytest.mark.asyncio
async def test_namespace_snapshot_symlink_does_not_escape_storage(tmp_path: Path) -> None:
    directory = tmp_path / "storage"
    directory.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside sentinel")
    (directory / "namespace.json").symlink_to(outside)
    namespace: NamespaceDriver = LocalNamespace(directory)

    with pytest.raises(StorageFailure):
        await namespace.get_root()

    assert outside.read_bytes() == b"outside sentinel"


@pytest.mark.asyncio
async def test_cancelled_content_stream_cleans_incomplete_files(tmp_path: Path) -> None:
    content: ContentDriver = LocalContent(tmp_path)

    async def cancelled() -> AsyncIterator[bytes]:
        yield b"partial"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await content.put(cancelled())

    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == ()


@pytest.mark.asyncio
async def test_independent_processes_share_root_without_losing_creations(tmp_path: Path) -> None:
    names = tuple(f"child-{index}" for index in range(8))
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
        roots = await asyncio.gather(*(
            loop.run_in_executor(pool, create_local_child_in_process, tmp_path, name)
            for name in names
        ))

    namespace: NamespaceDriver = LocalNamespace(tmp_path)
    root = await namespace.get_root()
    assert set(roots) == {str(root.id)}
    assert {node.name for node in await namespace.list_children(root.id)} == set(names)


@pytest.mark.asyncio
async def test_content_symlink_cannot_expose_external_bytes(tmp_path: Path) -> None:
    directory = tmp_path / "content"
    content: ContentDriver = LocalContent(directory)
    outside = tmp_path / "outside"
    outside.write_bytes(b"private bytes")
    key = "a" * 32
    (directory / key).symlink_to(outside)

    with pytest.raises(StorageFailure):
        async for _ in content.get(key):
            pytest.fail("External bytes must not be returned")

    assert outside.read_bytes() == b"private bytes"


@pytest.mark.asyncio
async def test_failed_namespace_publication_preserves_previous_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace: NamespaceDriver = LocalNamespace(tmp_path)
    root = await namespace.get_root()
    before = (tmp_path / "namespace.json").read_bytes()

    def fail_replace(source: str, destination: Path) -> None:
        raise OSError("injected publication failure")

    with monkeypatch.context() as patch:
        patch.setattr("umbod.infrastructure.filesystem.local_namespace.os.replace", fail_replace)
        with pytest.raises(StorageFailure):
            await namespace.create_node(
                root.id, "unpublished", NodeKind.FILE,
                NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
            )

    assert (tmp_path / "namespace.json").read_bytes() == before
    assert tuple(await namespace.list_children(root.id)) == ()
    assert not tuple(tmp_path.glob(".namespace-*"))


@pytest.mark.asyncio
async def test_cancelled_namespace_operation_finishes_before_returning_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace: NamespaceDriver = LocalNamespace(tmp_path)
    root = await namespace.get_root()
    descriptor = os.open(tmp_path / "namespace.lock", os.O_RDWR)
    original_flock = fcntl.flock
    original_flock(descriptor, fcntl.LOCK_EX)
    entered = Event()

    def observed_flock(file_descriptor: int, operation: int) -> None:
        entered.set()
        original_flock(file_descriptor, operation)

    monkeypatch.setattr("umbod.infrastructure.filesystem.local_namespace.fcntl.flock", observed_flock)
    task = asyncio.create_task(namespace.create_node(
        root.id, "committed", NodeKind.FILE,
        NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
    finally:
        original_flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert [node.name for node in await namespace.list_children(root.id)] == ["committed"]
