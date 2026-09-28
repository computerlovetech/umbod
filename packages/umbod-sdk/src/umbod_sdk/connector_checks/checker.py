import re
import tomllib
from typing import Protocol

from umbod_sdk.connector_checks.models import CheckResult, MetadataRequest
from umbod_sdk.connector_checks.port import MetadataReader

_ENTRY_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_TARGET = re.compile(rf"\s*{_IDENTIFIER}(?:\.{_IDENTIFIER})*\s*:\s*{_IDENTIFIER}(?:\.{_IDENTIFIER})*\s*\Z")
_GROUP = '[project.entry-points."umbod.connectors"]'


class MetadataCheckError(Exception):
    pass


class ConnectorMetadataChecker(Protocol):
    def check(self, request: MetadataRequest) -> CheckResult: ...


class EntryPointMetadataChecker:
    def __init__(self, reader: MetadataReader) -> None:
        self._reader = reader

    def check(self, request: MetadataRequest) -> CheckResult:
        path = f"{request.project_directory}/pyproject.toml"
        content = self._reader.read(request)
        try:
            document = tomllib.loads(content.text)
        except tomllib.TOMLDecodeError as error:
            raise MetadataCheckError(f"{path}: malformed TOML: {error}") from error

        project = document.get("project")
        if not isinstance(project, dict):
            raise MetadataCheckError(f"{path}: missing or malformed [project] table")
        groups = project.get("entry-points")
        if not isinstance(groups, dict):
            raise MetadataCheckError(f"{path}: missing or malformed [project.entry-points] table; add {_GROUP}")
        entries = groups.get("umbod.connectors")
        if not isinstance(entries, dict):
            raise MetadataCheckError(f"{path}: missing or malformed {_GROUP} table")
        if not entries:
            raise MetadataCheckError(f"{path}: {_GROUP} must contain at least one entry")

        for name, target in entries.items():
            if not _ENTRY_NAME.fullmatch(name):
                raise MetadataCheckError(f"{path}: {_GROUP} has invalid entry name {name!r}")
            if not isinstance(target, str) or not _TARGET.fullmatch(target):
                raise MetadataCheckError(
                    f"{path}: {_GROUP} entry {name!r} must be a module:exported_object target"
                )
        return CheckResult(entry_names=tuple(entries))
