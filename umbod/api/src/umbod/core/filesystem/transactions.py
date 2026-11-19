from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from .ports import AccessControlDriver, AccessControlReader, NamespaceDriver, NodeReader


@dataclass(frozen=True)
class FilesystemSession:
    namespace: NamespaceDriver
    access_control: AccessControlDriver


@dataclass(frozen=True)
class FilesystemReadSession:
    namespace: NodeReader
    access_control: AccessControlReader


class FilesystemTransactions(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[FilesystemSession]: ...
    def read(self) -> AbstractAsyncContextManager[FilesystemReadSession]: ...
