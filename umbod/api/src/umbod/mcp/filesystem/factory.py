from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.filesystem.content import ContentService, FilesystemContent
from umbod.core.filesystem.deletion import DeletionService, FilesystemDeletion
from umbod.core.persistence import Database
from umbod.core.filesystem.ports import ContentDriver
from umbod.core.filesystem.uploads import UploadService
from umbod.core.filesystem.uploads.service import SystemUploadClock
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.infrastructure import (
    create_filesystem_browsing, create_filesystem_creation, create_filesystem_sharing,
    create_filesystem_transactions, create_filesystem_uploads,
)

from .upload_models import MAX_UPLOAD_BYTES


class DatabaseFilesystemServiceFactory:
    def __init__(
        self, database: Database, content: ContentDriver, max_upload_bytes: int, managed_issuer: str,
    ) -> None:
        self._database = database
        self._managed_issuer = managed_issuer
        self._content = content
        self._max_upload_bytes = min(max_upload_bytes, MAX_UPLOAD_BYTES)

    def sharing(self) -> FilesystemSharing:
        return create_filesystem_sharing(
            database=self._database, resolver=VerifiedIdentityResolver(), issuer=self._managed_issuer,
        )

    def uploads(self) -> UploadService:
        return create_filesystem_uploads(
            database=self._database, resolver=VerifiedIdentityResolver(),
            content=self._content, max_upload_bytes=self._max_upload_bytes, clock=SystemUploadClock(),
        )

    def content(self) -> FilesystemContent:
        return ContentService(
            VerifiedIdentityResolver(), create_filesystem_transactions(database=self._database),
            self._content, self._max_upload_bytes,
        )

    def deletion(self) -> FilesystemDeletion:
        return DeletionService(
            VerifiedIdentityResolver(), create_filesystem_transactions(database=self._database),
        )

    def browsing(self) -> FilesystemBrowsing:
        return create_filesystem_browsing(
            database=self._database, resolver=VerifiedIdentityResolver()
        )

    def creation(self) -> FilesystemCreation:
        return create_filesystem_creation(
            database=self._database, resolver=VerifiedIdentityResolver()
        )
