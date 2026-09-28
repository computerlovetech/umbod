from pathlib import Path

from umbod_sdk.connector_checks.models import MetadataContent, MetadataRequest
from umbod_sdk.connector_checks.port import MetadataReadError


class InMemoryMetadataReader:
    def __init__(self, content: MetadataContent) -> None:
        self._content = content

    def read(self, request: MetadataRequest) -> MetadataContent:
        return self._content


class FileMetadataReader:
    def read(self, request: MetadataRequest) -> MetadataContent:
        path = Path(request.project_directory) / "pyproject.toml"
        try:
            return MetadataContent(text=path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as error:
            raise MetadataReadError(f"{path}: cannot read UTF-8 metadata: {error}") from error
