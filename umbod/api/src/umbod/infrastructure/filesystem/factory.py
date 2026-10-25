from typing import assert_never

from umbod.core.filesystem import (
    AccessControlDriver,
    ContentDriver,
    Filesystem,
    NamespaceDriver,
)
from umbod.core.filesystem.stores import DatabaseAccessControl, DatabaseNamespace
from umbod.core.persistence import Database

from .config import (
    ContentConfig,
    FilesystemConfig,
    InMemoryContentConfig,
    LocalContentConfig,
)


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
