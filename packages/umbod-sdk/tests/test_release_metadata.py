import hashlib
import json
from urllib.parse import urlencode

import pytest

from umbod_sdk.connector_checks.compatibility import (
    ReleaseMetadataError,
    ReleaseRequest,
    SdkReleaseMetadataReader,
)
from umbod_sdk.connector_checks.registry import RegistrySdkReleaseMetadataReader
from umbod_sdk.connector_checks.registry_transport import (
    RegistryRequest,
    RegistryResponse,
)

_LABEL = "org.opencontainers.image.umbod.sdk.version"
_REPOSITORIES = ("computerlovetech/umbod", "computerlovetech/umbod-connector-builder")


class MemoryRegistryTransport:
    def __init__(self) -> None:
        self.documents: dict[str, bytes] = {}
        self.calls: list[RegistryRequest] = []

    def get(self, request: RegistryRequest) -> RegistryResponse:
        self.calls.append(request)
        if request.url not in self.documents:
            raise ReleaseMetadataError("Registry release or metadata not found")
        return RegistryResponse(content=self.documents[request.url])

    def digest_document(self, repository: str, resource: str, document: dict[str, object]) -> str:
        content = json.dumps(document).encode()
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        self.documents[f"https://ghcr.io/v2/{repository}/{resource}/{digest}"] = content
        return digest

    def image(self, repository: str, version: str, architecture: str) -> str:
        digest = self.digest_document(repository, "blobs", {
            "os": "linux", "architecture": architecture, "config": {"Labels": {_LABEL: version} if version else {}},
        })
        return self.digest_document(repository, "manifests", {"schemaVersion": 2, "config": {"digest": digest}})

    def release(self, repository: str, tag: str, versions: dict[str, str]) -> None:
        query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
        self.documents[f"https://ghcr.io/token?{query}"] = b'{"token": "secret-token"}'
        manifests = [
            {"digest": self.image(repository, version, architecture), "platform": {"os": "linux", "architecture": architecture}}
            for architecture, version in versions.items()
        ]
        manifests.append({"digest": "sha256:" + "0" * 64, "platform": {"os": "unknown", "architecture": "unknown"}})
        self.documents[f"https://ghcr.io/v2/{repository}/manifests/{tag}"] = json.dumps({"schemaVersion": 2, "manifests": manifests}).encode()


@pytest.fixture
def registry() -> MemoryRegistryTransport:
    transport = MemoryRegistryTransport()
    for repository in _REPOSITORIES:
        transport.release(repository, "0.1.1-beta.1", {"amd64": "0.1.1b1", "arm64": "0.1.1b1"})
    return transport


def test_release_checks_core_builder_and_supported_platforms(registry: MemoryRegistryTransport) -> None:
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    assert reader.read(ReleaseRequest(release="0.1.1-beta.1")).version == "0.1.1b1"
    assert len(registry.calls) == 12
    assert all(call.token == "secret-token" for call in registry.calls if "/v2/" in call.url)
    assert all(not call.token for call in registry.calls if "/token?" in call.url)


@pytest.mark.parametrize("version", ["0.1.0", "0.1.1b2"])
def test_release_rejects_sdk_disagreement(registry: MemoryRegistryTransport, version: str) -> None:
    registry.release(_REPOSITORIES[1], "0.1.1-beta.1", {"amd64": "0.1.1b1", "arm64": version})
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="disagrees"):
        reader.read(ReleaseRequest(release="0.1.1-beta.1"))


def test_legacy_release_without_label_requires_explicit_sdk(registry: MemoryRegistryTransport) -> None:
    registry.release(_REPOSITORIES[0], "0.1.1-beta.1", {"amd64": ""})
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="--sdk-version"):
        reader.read(ReleaseRequest(release="0.1.1-beta.1"))


@pytest.mark.parametrize("tag", ["latest", "main-abcd", "../token", "0.1.1b1", "01.2.3", ""])
def test_invalid_release_fails_before_network(registry: MemoryRegistryTransport, tag: str) -> None:
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="immutable"):
        reader.read(ReleaseRequest(release=tag))
    assert not registry.calls


@pytest.mark.parametrize("body", [b"not json", b'{}', b'{"schemaVersion": 2, "manifests": []}', b'{"schemaVersion": 2, "config": {"digest": "../../token"}}'])
def test_malformed_registry_metadata_fails(registry: MemoryRegistryTransport, body: bytes) -> None:
    registry.documents[f"https://ghcr.io/v2/{_REPOSITORIES[0]}/manifests/0.1.1-beta.1"] = body
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError):
        reader.read(ReleaseRequest(release="0.1.1-beta.1"))


def test_corrupt_blob_digest_fails(registry: MemoryRegistryTransport) -> None:
    for url in registry.documents:
        if "/blobs/" in url:
            registry.documents[url] = b'{}'
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="digest"):
        reader.read(ReleaseRequest(release="0.1.1-beta.1"))


def test_single_platform_manifest_supported() -> None:
    registry = MemoryRegistryTransport()
    for repository in _REPOSITORIES:
        registry.release(repository, "1.2.3", {"amd64": "1.2.3"})
        digest = registry.image(repository, "1.2.3", "amd64")
        registry.documents[f"https://ghcr.io/v2/{repository}/manifests/1.2.3"] = registry.documents[f"https://ghcr.io/v2/{repository}/manifests/{digest}"]
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    assert reader.read(ReleaseRequest(release="1.2.3")).version == "1.2.3"


def test_null_legacy_labels_provide_explicit_sdk_guidance(registry: MemoryRegistryTransport) -> None:
    repository = _REPOSITORIES[0]
    digest = registry.digest_document(repository, "blobs", {
        "os": "linux", "architecture": "amd64", "config": {"Labels": None},
    })
    registry.documents[f"https://ghcr.io/v2/{repository}/manifests/0.1.1-beta.1"] = json.dumps({
        "schemaVersion": 2, "config": {"digest": digest},
    }).encode()
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="--sdk-version"):
        reader.read(ReleaseRequest(release="0.1.1-beta.1"))


def test_missing_release_is_not_treated_as_compatible(registry: MemoryRegistryTransport) -> None:
    reader: SdkReleaseMetadataReader = RegistrySdkReleaseMetadataReader(registry)
    with pytest.raises(ReleaseMetadataError, match="not found"):
        reader.read(ReleaseRequest(release="1.0.0"))
