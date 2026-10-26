from collections.abc import Sequence
from typing import Protocol

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation


class FilesystemGroupClaimFields(Protocol):
    def claim_fields(self) -> Sequence[str]: ...


class FilesystemCallerCapture(Protocol):
    def capture(self) -> CallerSnapshot: ...


class FilesystemServiceFactory(Protocol):
    def browsing(self) -> FilesystemBrowsing: ...

    def creation(self) -> FilesystemCreation: ...
