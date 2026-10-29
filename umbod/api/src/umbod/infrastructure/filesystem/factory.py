from datetime import timedelta
from typing import assert_never

from umbod.core.filesystem import (
    AccessControlDriver,
    CreationService,
    FilesystemCreation,
    FilesystemTransactions,
    RootProvisioning,
    RootProvisioningService,
    ContentDriver,
    Filesystem,
    NamespaceDriver,
)
from umbod.core.filesystem.authorization import AuthorizationService, FilesystemIdentityResolver
from umbod.core.filesystem.browsing import BrowsingService, FilesystemBrowsing
from umbod.core.filesystem.stores import DatabaseAccessControl, DatabaseNamespace, DatabaseFilesystemTransactions
from umbod.core.persistence import Database
from umbod.core.filesystem.uploads import UploadClock, UploadService
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions

from umbod.core.filesystem.administration import RootGroupPolicyManagement, RootGroupPolicyService
from umbod.core.filesystem.stores.administration import DatabaseRootPolicyTransactions

from .config import (
    ContentConfig,
    FilesystemConfig,
    InMemoryContentConfig,
    LocalContentConfig,
)


def create_filesystem_browsing(
    *, database: Database, resolver: FilesystemIdentityResolver
) -> FilesystemBrowsing:
    namespace = create_namespace_driver(database=database)
    return BrowsingService(
        namespace=namespace,
        resolver=resolver,
        transactions=create_filesystem_transactions(database=database),
        authorization=AuthorizationService(
            resolver=resolver,
            namespace=namespace,
            access_control=create_access_control_driver(database=database),
        ),
    )


def create_filesystem_transactions(*, database: Database) -> FilesystemTransactions:
    return DatabaseFilesystemTransactions(database)


def create_filesystem_creation(
    *, database: Database, resolver: FilesystemIdentityResolver
) -> FilesystemCreation:
    return CreationService(resolver, create_filesystem_transactions(database=database))


def create_filesystem_uploads(
    *, database: Database, resolver: FilesystemIdentityResolver, content: ContentDriver,
    max_upload_bytes: int, clock: UploadClock,
) -> UploadService:
    return UploadService(
        resolver, DatabaseUploadTransactions(database), content, max_upload_bytes, clock,
        timedelta(hours=1),
    )


def create_root_group_policy_management(*, database: Database, issuer: str) -> RootGroupPolicyManagement:
    return RootGroupPolicyService(DatabaseRootPolicyTransactions(database), issuer)


def create_root_provisioning(*, database: Database) -> RootProvisioning:
    return RootProvisioningService(create_filesystem_transactions(database=database))


def create_namespace_driver(*, database: Database) -> NamespaceDriver:
    return DatabaseNamespace(database)


def create_access_control_driver(*, database: Database) -> AccessControlDriver:
    return DatabaseAccessControl(database)


def create_content_driver(config: ContentConfig) -> ContentDriver:
    if isinstance(config, InMemoryContentConfig):
        from .inmemory import InMemoryContent

        return InMemoryContent()
    if isinstance(config, LocalContentConfig):
        from .local_content import LocalContent

        return LocalContent(config.directory)
    assert_never(config)


def create_filesystem(config: FilesystemConfig, *, database: Database) -> Filesystem:
    return Filesystem(
        namespace=create_namespace_driver(database=database),
        content=create_content_driver(config.content),
    )
