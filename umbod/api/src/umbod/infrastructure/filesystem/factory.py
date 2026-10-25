from typing import assert_never

from umbod.core.filesystem.ports import ContentDriver, NamespaceDriver
from umbod.core.filesystem.service import Filesystem

from .config import (
    ContentConfig,
    InMemoryContentConfig,
    InMemoryNamespaceConfig,
    LocalContentConfig,
    LocalNamespaceConfig,
    NamespaceConfig,
    FilesystemConfig,
)


def create_namespace_driver(config: NamespaceConfig) -> NamespaceDriver:
    if isinstance(config, InMemoryNamespaceConfig):
        from .inmemory import InMemoryNamespace

        return InMemoryNamespace()
    if isinstance(config, LocalNamespaceConfig):
        from .local_namespace import LocalNamespace

        return LocalNamespace(config.directory)
    assert_never(config)


def create_content_driver(config: ContentConfig) -> ContentDriver:
    if isinstance(config, InMemoryContentConfig):
        from .inmemory import InMemoryContent

        return InMemoryContent()
    if isinstance(config, LocalContentConfig):
        from .local_content import LocalContent

        return LocalContent(config.directory)
    assert_never(config)


def create_filesystem(config: FilesystemConfig) -> Filesystem:
    return Filesystem(
        namespace=create_namespace_driver(config.namespace),
        content=create_content_driver(config.content),
    )
