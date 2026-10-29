from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.persistence import Database
from umbod.core.filesystem.ports import ContentDriver
from umbod.core.filesystem.uploads import UploadService
from umbod.core.filesystem.uploads.service import SystemUploadClock
from umbod.infrastructure import create_filesystem_uploads

from .upload_models import MAX_UPLOAD_BYTES
from umbod.infrastructure import create_filesystem_browsing, create_filesystem_creation


class DatabaseFilesystemServiceFactory:
    def __init__(self, database: Database, content: ContentDriver, max_upload_bytes: int) -> None:
        self._database = database
        self._content = content
        self._max_upload_bytes = min(max_upload_bytes, MAX_UPLOAD_BYTES)

    def uploads(self) -> UploadService:
        return create_filesystem_uploads(
            database=self._database, resolver=VerifiedIdentityResolver(),
            content=self._content, max_upload_bytes=self._max_upload_bytes, clock=SystemUploadClock(),
        )

    def browsing(self) -> FilesystemBrowsing:
        return create_filesystem_browsing(
            database=self._database, resolver=VerifiedIdentityResolver()
        )

    def creation(self) -> FilesystemCreation:
        return create_filesystem_creation(
            database=self._database, resolver=VerifiedIdentityResolver()
        )
