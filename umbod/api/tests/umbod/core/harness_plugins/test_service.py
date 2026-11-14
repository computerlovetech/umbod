import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from umbod.core.harness_plugins.ports import PackageResources
from umbod.core.harness_plugins.service import HarnessPackageService


class InMemoryPackageResourceReader:
    def __init__(self, resources: PackageResources) -> None:
        self._resources = resources

    def read(self) -> PackageResources:
        return self._resources


def test_service_renders_injected_resources_and_hashes_exact_zip() -> None:
    reader = InMemoryPackageResourceReader(PackageResources(skill="canonical skill", license_text="MIT"))
    service = HarnessPackageService("https://configured.test/", reader)
    package = service.package("claude-code")
    assert service.checksum("claude-code") == hashlib.sha256(package).hexdigest()
    with ZipFile(BytesIO(package)) as archive:
        assert archive.read("plugins/umbod/skills/umbod-connected-apps/SKILL.md") == b"canonical skill"
        assert archive.read("plugins/umbod/LICENSE") == b"MIT"


@pytest.mark.parametrize("skill", ["", " ", "x" * 262145])
def test_resource_boundary_rejects_empty_or_unbounded_content(skill: str) -> None:
    with pytest.raises(ValidationError):
        PackageResources(skill=skill, license_text="MIT")
