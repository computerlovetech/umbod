from collections.abc import Sequence
from enum import Enum
from typing import Protocol, Union, runtime_checkable

from fastmcp.tools import InputRequiredToolResult

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import FilesystemBrowsing, NodeSummary
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.updates import FilesystemNodeUpdates
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.homes import HomeService
from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.uploads import UploadService
from umbod.core.filesystem.sharing import FilesystemSharing

from .models import DeleteFileCommand


class FileDeletionApproval(Enum):
    APPROVED = "approved"


class FilesystemDeletionApproval(Protocol):
    async def confirm(
        self, caller: CallerSnapshot, command: DeleteFileCommand, node: NodeSummary,
    ) -> Union[FileDeletionApproval, InputRequiredToolResult]: ...


@runtime_checkable
class ClosableByteStream(Protocol):
    async def aclose(self) -> None: ...


class FilesystemGroupClaimFields(Protocol):
    def claim_fields(self) -> Sequence[str]: ...


class FilesystemCallerCapture(Protocol):
    def capture(self) -> CallerSnapshot: ...


class FilesystemServiceFactory(Protocol):
    def read_max_bytes(self) -> int: ...

    def homes(self) -> HomeService: ...

    def access(self) -> AccessMetadataService: ...

    def sharing(self) -> FilesystemSharing: ...

    def browsing(self) -> FilesystemBrowsing: ...

    def creation(self) -> FilesystemCreation: ...

    def uploads(self) -> UploadService: ...

    def upload_sessions(self) -> UploadService: ...

    def upload_api_origin(self) -> str: ...

    def updates(self) -> FilesystemNodeUpdates: ...

    def deletion(self) -> FilesystemDeletion: ...

    def content(self) -> FilesystemContent: ...
