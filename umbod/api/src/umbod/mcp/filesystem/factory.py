from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.persistence import Database
from umbod.infrastructure import create_filesystem_browsing, create_filesystem_creation


class DatabaseFilesystemServiceFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    def browsing(self) -> FilesystemBrowsing:
        return create_filesystem_browsing(
            database=self._database, resolver=VerifiedIdentityResolver()
        )

    def creation(self) -> FilesystemCreation:
        return create_filesystem_creation(
            database=self._database, resolver=VerifiedIdentityResolver()
        )
