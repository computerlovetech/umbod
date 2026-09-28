from umbod_sdk.connector_checks.checker import (
    ConnectorMetadataChecker,
    EntryPointMetadataChecker,
    MetadataCheckError,
)
from umbod_sdk.connector_checks.compatibility import (
    ConnectorCompatibilityChecker,
    SdkCompatibilityChecker,
    SdkReleaseMetadataReader,
)
from umbod_sdk.connector_checks.models import (
    CheckResult,
    MetadataContent,
    MetadataRequest,
)
from umbod_sdk.connector_checks.port import MetadataReader, MetadataReadError
from umbod_sdk.connector_checks.readers import (
    FileMetadataReader,
    InMemoryMetadataReader,
)
from umbod_sdk.connector_checks.registry import RegistrySdkReleaseMetadataReader
from umbod_sdk.connector_checks.registry_transport import HttpRegistryTransport


def create_checker() -> ConnectorMetadataChecker:
    return EntryPointMetadataChecker(FileMetadataReader())


def create_compatibility_checker() -> SdkCompatibilityChecker:
    return ConnectorCompatibilityChecker(FileMetadataReader())


def create_release_reader() -> SdkReleaseMetadataReader:
    return RegistrySdkReleaseMetadataReader(HttpRegistryTransport())


__all__ = [
    "CheckResult",
    "ConnectorMetadataChecker",
    "EntryPointMetadataChecker",
    "FileMetadataReader",
    "InMemoryMetadataReader",
    "MetadataCheckError",
    "MetadataContent",
    "MetadataReadError",
    "MetadataReader",
    "MetadataRequest",
    "create_checker",
    "create_compatibility_checker",
    "create_release_reader",
]
