from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from .ports import AccessControlDriver, NamespaceDriver


@dataclass(frozen=True)
class FilesystemSession:
    namespace: NamespaceDriver
    access_control: AccessControlDriver


class FilesystemTransactions(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[FilesystemSession]: ...
