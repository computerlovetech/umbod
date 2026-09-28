from typing import Protocol

from umbod_sdk.connector_init.models import InitRequest, ProjectSnapshot


class InitError(ValueError):
    pass


class ProjectFiles(Protocol):
    def inspect(self, request: InitRequest) -> ProjectSnapshot: ...

    def create_module(self, request: InitRequest, source: bytes) -> None: ...

    def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None: ...
