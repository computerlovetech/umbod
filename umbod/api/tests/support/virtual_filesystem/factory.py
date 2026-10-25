from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import cast
from uuid import uuid4

from umbod.core.virtual_filesystem import EmptyContent, RootParent, UnspecifiedContentType

from .dependencies import InMemoryContent, InMemoryNamespace
from .language import FilesystemDsl
from .models import NodeHandle
from .protocols import (
    ContentRefFactory,
    FilesystemFactory,
    FilesystemLanguage,
    FilesystemObservations,
    MetadataFactory,
    NamespaceEvidence,
    NodeFactory,
    PublicKind,
)
from .python_driver import DirectPythonAcceptanceDriver


@dataclass(frozen=True)
class FilesystemAcceptanceContext:
    filesystem: FilesystemLanguage
    other_caller: FilesystemLanguage
    observations: FilesystemObservations
    namespace_evidence: NamespaceEvidence
    supplied_root: NodeHandle


def create_acceptance_context() -> FilesystemAcceptanceContext:
    production = import_module("umbod.core.virtual_filesystem")
    node_factory = cast(NodeFactory, production.Node)
    metadata_factory = cast(MetadataFactory, production.NodeMetadata)
    content_ref_factory = cast(ContentRefFactory, production.ContentRef)
    service_factory = cast(FilesystemFactory, production.VirtualFilesystem)
    directory_kind = cast(PublicKind, production.NodeKind.DIRECTORY)
    timestamp = datetime.now(timezone.utc)
    root = node_factory(
        id=uuid4(), parent_id=RootParent(), name="", kind=directory_kind,
        metadata=metadata_factory(content_type=UnspecifiedContentType(), attributes={}),
        content=EmptyContent(),
        created_at=timestamp, updated_at=timestamp, revision=1,
    )
    namespace = InMemoryNamespace(root, node_factory)
    content = InMemoryContent(content_ref_factory)
    driver = DirectPythonAcceptanceDriver(
        service_factory(namespace=namespace, content=content),
        namespace, content, metadata_factory,
    )
    other_driver = DirectPythonAcceptanceDriver(
        service_factory(namespace=namespace, content=content),
        namespace, content, metadata_factory,
    )
    return FilesystemAcceptanceContext(
        filesystem=FilesystemDsl(driver), other_caller=FilesystemDsl(other_driver),
        observations=driver, namespace_evidence=namespace,
        supplied_root=NodeHandle(str(root.id)),
    )
