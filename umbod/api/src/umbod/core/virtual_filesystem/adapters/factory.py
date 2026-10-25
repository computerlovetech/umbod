from typing import assert_never

from ..config import (
    ContentConfig,
    InMemoryContentConfig,
    InMemoryNamespaceConfig,
    LocalContentConfig,
    LocalNamespaceConfig,
    NamespaceConfig,
    VirtualFilesystemConfig,
)
from ..ports import ContentDriver, NamespaceDriver
from ..service import VirtualFilesystem
from .inmemory import InMemoryContent, InMemoryNamespace
from .local_content import LocalContent
from .local_namespace import LocalNamespace


def create_namespace_driver(config: NamespaceConfig) -> NamespaceDriver:
    if isinstance(config, InMemoryNamespaceConfig):
        return InMemoryNamespace()
    if isinstance(config, LocalNamespaceConfig):
        return LocalNamespace(config.directory)
    assert_never(config)


def create_content_driver(config: ContentConfig) -> ContentDriver:
    if isinstance(config, InMemoryContentConfig):
        return InMemoryContent()
    if isinstance(config, LocalContentConfig):
        return LocalContent(config.directory)
    assert_never(config)


def create_virtual_filesystem(config: VirtualFilesystemConfig) -> VirtualFilesystem:
    return VirtualFilesystem(
        namespace=create_namespace_driver(config.namespace),
        content=create_content_driver(config.content),
    )
