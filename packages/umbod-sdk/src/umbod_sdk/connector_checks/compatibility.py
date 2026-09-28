import re
import tomllib
from typing import Protocol

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict

from umbod_sdk.connector_checks.checker import (
    EntryPointMetadataChecker,
    MetadataCheckError,
)
from umbod_sdk.connector_checks.models import MetadataRequest
from umbod_sdk.connector_checks.port import MetadataReader
from umbod_sdk.connector_checks.readers import InMemoryMetadataReader


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    release: str


class SdkVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str


class CompatibilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sdk_version: str
    requirement: str
    compatible: bool


class ReleaseMetadataError(Exception):
    pass


class SdkReleaseMetadataReader(Protocol):
    def read(self, request: ReleaseRequest) -> SdkVersion: ...


class SdkCompatibilityChecker(Protocol):
    def check(self, request: MetadataRequest, candidate: SdkVersion) -> CompatibilityResult: ...


def sdk_version_for_release(release: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-beta\.(?:0|[1-9]\d*))?", release):
        raise ReleaseMetadataError("Target must be an immutable X.Y.Z or X.Y.Z-beta.N image release")
    return str(Version(release.replace("-beta.", "b")))


class InMemorySdkReleaseMetadataReader:
    def __init__(self, versions: dict[str, SdkVersion]) -> None:
        self._versions = versions

    def read(self, request: ReleaseRequest) -> SdkVersion:
        sdk_version_for_release(request.release)
        try:
            return self._versions[request.release]
        except KeyError as error:
            raise ReleaseMetadataError(f"Release {request.release}: no SDK version metadata available") from error


def _sdk_requirement(project: dict[str, object], path: str) -> Requirement:
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list) or any(not isinstance(item, str) for item in dynamic):
        raise MetadataCheckError(f"{path}: [project].dynamic must be a list of strings")
    if "dependencies" in dynamic:
        raise MetadataCheckError(f"{path}: dynamic dependencies are unsupported; declare umbod in [project].dependencies")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        raise MetadataCheckError(f"{path}: [project].dependencies must be a static list of requirement strings including umbod")
    requirements: list[Requirement] = []
    for item in dependencies:
        try:
            requirement = Requirement(item)
        except InvalidRequirement as error:
            raise MetadataCheckError(f"{path}: malformed dependency {item!r}: {error}") from error
        if canonicalize_name(requirement.name) == "umbod":
            requirements.append(requirement)
    if len(requirements) != 1:
        raise MetadataCheckError(f"{path}: declare exactly one direct umbod dependency; missing or duplicate declarations cannot be checked")
    return requirements[0]


def _validate_requirement(requirement: Requirement, path: str) -> None:
    if requirement.url:
        raise MetadataCheckError(f"{path}: direct URL umbod requirement is unsupported; declare a version range")
    if requirement.marker:
        raise MetadataCheckError(f"{path}: conditional umbod requirement is unsupported for target platforms; declare an unconditional range")
    if not requirement.specifier:
        raise MetadataCheckError(f"{path}: umbod needs a version specifier for a meaningful check")


class ConnectorCompatibilityChecker:
    def __init__(self, metadata: MetadataReader) -> None:
        self._metadata = metadata

    def check(self, request: MetadataRequest, candidate: SdkVersion) -> CompatibilityResult:
        try:
            version = Version(candidate.version)
        except InvalidVersion as error:
            raise MetadataCheckError(f"Invalid SDK version {candidate.version!r}") from error
        content = self._metadata.read(request)
        EntryPointMetadataChecker(InMemoryMetadataReader(content)).check(request)
        project = tomllib.loads(content.text)["project"]
        path = f"{request.project_directory}/pyproject.toml"
        requirement = _sdk_requirement(project, path)
        _validate_requirement(requirement, path)
        return CompatibilityResult(
            sdk_version=str(version),
            requirement=str(requirement),
            compatible=requirement.specifier.contains(version, prereleases=True),
        )
