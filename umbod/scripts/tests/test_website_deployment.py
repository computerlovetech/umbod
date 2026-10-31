import json
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def repository() -> Path:
    return Path(__file__).resolve().parents[3]


def test_production_and_preview_deploy_to_separate_workers_and_domains(repository: Path) -> None:
    config = json.loads((repository / "website/wrangler.jsonc").read_text())
    preview = config["env"]["preview"]
    assert config["name"] == "umbod-website"
    assert config["routes"] == [{"pattern": "umbod.ai", "custom_domain": True}]
    assert preview["name"] == "umbod-website-preview"
    assert preview["routes"] == [{"pattern": "preview.umbod.ai", "custom_domain": True}]
    assert preview["assets"] == config["assets"]


def test_website_ci_validates_without_deploying_or_requiring_cloudflare_secrets(repository: Path) -> None:
    workflow: dict[str, Any] = yaml.load(
        (repository / ".github/workflows/website-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["jobs"]) == {"harness-linting", "website"}
    assert "CLOUDFLARE_API_TOKEN" not in str(workflow)
    assert "wrangler deploy" not in str(workflow)
    assert workflow["jobs"]["website"]["steps"][-1]["run"] == "bun run build"


def test_release_workflow_does_not_require_cloudflare_credentials(repository: Path) -> None:
    workflow = (repository / ".github/workflows/umbod-release.yml").read_text()
    assert "CLOUDFLARE_" not in workflow
    assert "wrangler deploy" not in workflow
