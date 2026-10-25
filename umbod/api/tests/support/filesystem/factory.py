from dataclasses import dataclass

from umbod.core.filesystem import ContentDriver, NamespaceDriver, Filesystem

from .dependencies import RecordingNamespace
from .language import FilesystemDsl
from .models import NodeHandle
from .protocols import FilesystemLanguage, FilesystemObservations, NamespaceEvidence
from .python_driver import DirectPythonAcceptanceDriver


@dataclass(frozen=True)
class FilesystemAcceptanceContext:
    filesystem: FilesystemLanguage
    other_caller: FilesystemLanguage
    observations: FilesystemObservations
    namespace_evidence: NamespaceEvidence
    supplied_root: NodeHandle


async def create_acceptance_context(
    namespace: NamespaceDriver, content: ContentDriver,
) -> FilesystemAcceptanceContext:
    root = await namespace.get_root()
    recording = RecordingNamespace(namespace)
    driver = DirectPythonAcceptanceDriver(
        Filesystem(namespace=recording, content=content), recording, content,
    )
    other_driver = DirectPythonAcceptanceDriver(
        Filesystem(namespace=recording, content=content), recording, content,
    )
    return FilesystemAcceptanceContext(
        filesystem=FilesystemDsl(driver), other_caller=FilesystemDsl(other_driver),
        observations=driver, namespace_evidence=recording,
        supplied_root=NodeHandle(str(root.id)),
    )
