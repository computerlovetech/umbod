import hashlib
from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from umbod_sdk.connector_checks.compatibility import (
    ReleaseMetadataError,
    ReleaseRequest,
    SdkVersion,
    sdk_version_for_release,
)
from umbod_sdk.connector_checks.registry_transport import (
    RegistryRequest,
    RegistryTransport,
)

_DIGEST = Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{64}$")]
_LABEL = "org.opencontainers.image.umbod.sdk.version"
_ACCEPT = (
    "application/vnd.oci.image.index.v1+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.docker.distribution.manifest.v2+json"
)


class _Token(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str = Field(validation_alias=AliasChoices("token", "access_token"), min_length=1)


class _Descriptor(BaseModel):
    model_config = ConfigDict(strict=True)

    digest: _DIGEST
    platform: dict[str, str] = Field(default_factory=dict)


class _Index(BaseModel):
    model_config = ConfigDict(strict=True)

    schemaVersion: Literal[2]
    manifests: list[_Descriptor]


class _Manifest(BaseModel):
    model_config = ConfigDict(strict=True)

    schemaVersion: Literal[2]
    config: _Descriptor


class _ImageSettings(BaseModel):
    model_config = ConfigDict(strict=True)

    Labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("Labels", mode="before")
    @classmethod
    def normalize_absent_labels(cls, value: object) -> object:
        return {} if value is None else value


class _ImageConfig(BaseModel):
    model_config = ConfigDict(strict=True)

    os: str
    architecture: str
    config: _ImageSettings


class RegistrySdkReleaseMetadataReader:
    def __init__(self, transport: RegistryTransport) -> None:
        self._transport = transport

    def _read(self, url: str, token: str) -> bytes:
        return self._transport.get(RegistryRequest(url=url, token=token, accept=_ACCEPT)).content

    def _by_digest(self, repository: str, resource: str, digest: str, token: str) -> bytes:
        content = self._read(f"https://ghcr.io/v2/{repository}/{resource}/{digest}", token)
        if f"sha256:{hashlib.sha256(content).hexdigest()}" != digest:
            raise ReleaseMetadataError("Registry metadata digest does not match its descriptor")
        return content

    def _config_version(self, repository: str, manifest: bytes, token: str, platform: dict[str, str]) -> str:
        leaf = _Manifest.model_validate_json(manifest)
        config = _ImageConfig.model_validate_json(self._by_digest(repository, "blobs", leaf.config.digest, token))
        if config.os != "linux" or config.architecture not in {"amd64", "arm64"}:
            raise ReleaseMetadataError("Release must contain a supported linux/amd64 or linux/arm64 image")
        if platform and (config.os != platform.get("os") or config.architecture != platform.get("architecture")):
            raise ReleaseMetadataError("Registry image platform does not match its manifest descriptor")
        version = config.config.Labels.get(_LABEL)
        if not version:
            raise ReleaseMetadataError(
                f"{repository} has no synchronized SDK-version label; older releases cannot be inferred from their tag. "
                "Obtain the SDK version from the target runtime and use --sdk-version instead."
            )
        return version

    def _image_versions(self, repository: str, request: ReleaseRequest) -> set[str]:
        query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
        token = _Token.model_validate_json(self._read(f"https://ghcr.io/token?{query}", "")).token
        manifest = self._read(f"https://ghcr.io/v2/{repository}/manifests/{request.release}", token)
        try:
            index = _Index.model_validate_json(manifest)
        except ValidationError:
            return {self._config_version(repository, manifest, token, {})}
        platforms = [item for item in index.manifests if item.platform.get("os") == "linux" and item.platform.get("architecture") in {"amd64", "arm64"}]
        if not platforms or len(platforms) > 8:
            raise ReleaseMetadataError("Release index has no supported images or too many platform manifests")
        return {
            self._config_version(
                repository, self._by_digest(repository, "manifests", item.digest, token), token, item.platform,
            )
            for item in platforms
        }

    def read(self, request: ReleaseRequest) -> SdkVersion:
        expected = sdk_version_for_release(request.release)
        try:
            versions = set().union(*(self._image_versions(repository, request) for repository in (
                "computerlovetech/umbod", "computerlovetech/umbod-connector-builder",
            )))
        except ValidationError as error:
            raise ReleaseMetadataError("Registry returned malformed release metadata; no compatibility verdict available") from error
        if versions != {expected}:
            raise ReleaseMetadataError(f"Published SDK metadata disagrees with synchronized target {request.release}; expected SDK {expected}")
        return SdkVersion(version=expected)
