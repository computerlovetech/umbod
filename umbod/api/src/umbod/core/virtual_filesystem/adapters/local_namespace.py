import fcntl
import os
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from umbod.core.virtual_filesystem import (
    ContentRef,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    StorageFailure,
)
from umbod.core.virtual_filesystem.namespace import (
    ROOT_ID,
    NamespaceState,
    create_node,
    get_node,
    initial_state,
    list_children,
    update_node,
)

from .io import complete_io
from .objects import open_regular, prepare_directory, sync_directory

T = TypeVar("T")


class LocalNamespace:
    def __init__(self, directory: Path) -> None:
        self._directory = prepare_directory(directory)

    async def get_root(self) -> Node:
        return await self.get_node(ROOT_ID)

    async def get_node(self, node_id: NodeId) -> Node:
        return await complete_io(partial(
            self._transaction, lambda state: (state, get_node(state, node_id)), False,
        ))

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        return await complete_io(partial(
            self._transaction, lambda state: (state, list_children(state, parent_id)), False,
        ))

    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata,
    ) -> Node:
        operation = partial(
            create_node, parent_id=parent_id, name=name, kind=kind,
            metadata=metadata.model_copy(deep=True),
        )
        return await complete_io(partial(self._transaction, operation, True))

    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int,
    ) -> Node:
        operation = partial(
            update_node, node_id=node_id, content=content.model_copy(deep=True),
            expected_revision=expected_revision,
        )
        return await complete_io(partial(self._transaction, operation, True))

    def _transaction(
        self, operation: Callable[[NamespaceState], tuple[NamespaceState, T]], persist: bool,
    ) -> T:
        try:
            descriptor = open_regular(self._directory / "namespace.lock", os.O_RDWR | os.O_CREAT)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                state = self._load()
                updated, result = operation(state)
                if persist:
                    self._save(updated)
                return result
            finally:
                os.close(descriptor)
        except (OSError, ValidationError, ValueError) as error:
            raise StorageFailure("Namespace storage operation failed") from error

    def _load(self) -> NamespaceState:
        try:
            descriptor = open_regular(self._directory / "namespace.json", os.O_RDONLY)
        except FileNotFoundError:
            state = initial_state()
            self._save(state)
            return state
        with os.fdopen(descriptor, "rb") as snapshot:
            return NamespaceState.model_validate_json(snapshot.read())

    def _save(self, state: NamespaceState) -> None:
        destination = self._directory / "namespace.json"
        if destination.is_symlink():
            raise StorageFailure("Namespace snapshot must not be a symlink")
        descriptor, temporary = tempfile.mkstemp(prefix=".namespace-", dir=self._directory)
        try:
            with os.fdopen(descriptor, "wb") as snapshot:
                snapshot.write(state.model_dump_json().encode("utf-8"))
                snapshot.flush()
                os.fsync(snapshot.fileno())
            os.replace(temporary, destination)
            sync_directory(self._directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
