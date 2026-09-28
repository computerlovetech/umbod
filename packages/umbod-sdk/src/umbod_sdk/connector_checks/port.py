from typing import Protocol

from umbod_sdk.connector_checks.models import MetadataContent, MetadataRequest


class MetadataReadError(Exception):
    pass


class MetadataReader(Protocol):
    def read(self, request: MetadataRequest) -> MetadataContent: ...
