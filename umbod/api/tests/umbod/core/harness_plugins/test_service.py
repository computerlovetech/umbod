import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from umbod.core.harness_plugins.ports import PackageResources
from umbod.core.harness_plugins.rendering import Harness
from umbod.core.harness_plugins.service import HarnessPackageService


class InMemoryPackageResourceReader:
    def __init__(self, resources: PackageResources) -> None:
        self._resources = resources

    def read(self) -> PackageResources:
        return self._resources


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_service_renders_injected_resources_and_hashes_exact_zip(harness: Harness) -> None:
    reader = InMemoryPackageResourceReader(
        PackageResources(
            run_diagnostics_skill="run diagnostics skill", license_text="MIT",
        ),
    )
    service = HarnessPackageService("https://configured.test/", reader)
    package = service.package(harness)
    assert service.checksum(harness) == hashlib.sha256(package).hexdigest()
    with ZipFile(BytesIO(package)) as archive:
        assert archive.read("plugins/umbod/skills/run-diagnostics/SKILL.md") == b"run diagnostics skill"
        assert archive.read("plugins/umbod/LICENSE") == b"MIT"


@pytest.mark.parametrize("content", ["", " ", "x" * 262145], ids=["empty", "blank", "oversized"])
def test_resource_boundary_rejects_invalid_skill_content(content: str) -> None:
    with pytest.raises(ValidationError) as error:
        PackageResources(run_diagnostics_skill=content, license_text="MIT")
    assert [detail["loc"] for detail in error.value.errors()] == [("run_diagnostics_skill",)]


def test_resource_boundary_requires_the_diagnostic_skill() -> None:
    with pytest.raises(ValidationError) as error:
        PackageResources.model_validate({"license_text": "MIT"})
    assert [detail["loc"] for detail in error.value.errors()] == [("run_diagnostics_skill",)]
