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
            skill="canonical skill", behaviour_skill="behaviour skill",
            run_diagnostics_skill="run diagnostics skill", license_text="MIT",
        ),
    )
    service = HarnessPackageService("https://configured.test/", reader)
    package = service.package(harness)
    assert service.checksum(harness) == hashlib.sha256(package).hexdigest()
    with ZipFile(BytesIO(package)) as archive:
        assert archive.read("plugins/umbod/skills/umbod-connected-apps/SKILL.md") == b"canonical skill"
        assert archive.read("plugins/umbod/skills/umbod-agent-behaviour/SKILL.md") == b"behaviour skill"
        assert archive.read("plugins/umbod/skills/run-diagnostics/SKILL.md") == b"run diagnostics skill"
        assert archive.read("plugins/umbod/LICENSE") == b"MIT"


@pytest.mark.parametrize("field", ["skill", "behaviour_skill", "run_diagnostics_skill"])
@pytest.mark.parametrize("content", ["", " ", "x" * 262145], ids=["empty", "blank", "oversized"])
def test_resource_boundary_rejects_invalid_skill_content(field: str, content: str) -> None:
    resources = {
        "skill": "canonical skill",
        "behaviour_skill": "behaviour skill",
        "run_diagnostics_skill": "run diagnostics skill",
        "license_text": "MIT",
    }
    resources[field] = content
    with pytest.raises(ValidationError) as error:
        PackageResources.model_validate(resources)
    assert [detail["loc"] for detail in error.value.errors()] == [(field,)]


@pytest.mark.parametrize("field", ["behaviour_skill", "run_diagnostics_skill"])
def test_resource_boundary_requires_each_auxiliary_skill(field: str) -> None:
    resources = {
        "skill": "canonical skill",
        "behaviour_skill": "behaviour skill",
        "run_diagnostics_skill": "run diagnostics skill",
        "license_text": "MIT",
    }
    del resources[field]
    with pytest.raises(ValidationError) as error:
        PackageResources.model_validate(resources)
    assert [detail["loc"] for detail in error.value.errors()] == [(field,)]
