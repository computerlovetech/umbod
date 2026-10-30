from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.uploads import UploadService
from umbod.core.filesystem.sharing import FilesystemSharing


@runtime_checkable
class ClosableByteStream(Protocol):
    async def aclose(self) -> None: ...


class FilesystemGroupClaimFields(Protocol):
    def claim_fields(self) -> Sequence[str]: ...


class FilesystemCallerCapture(Protocol):
    def capture(self) -> CallerSnapshot: ...


class FilesystemServiceFactory(Protocol):
    def sharing(self) -> FilesystemSharing: ...

    def browsing(self) -> FilesystemBrowsing: ...

    def creation(self) -> FilesystemCreation: ...

    def uploads(self) -> UploadService: ...

    def deletion(self) -> FilesystemDeletion: ...

    def content(self) -> FilesystemContent: ...
