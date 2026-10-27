import subprocess
import sys
from pathlib import Path

import pytest
from check_module_readmes import find_module_readmes, validate_readme


SCRIPT = Path(__file__).resolve().parents[3] / "skills" / "development" / "write-module-readme" / "scripts" / "check_module_readmes.py"


@pytest.mark.parametrize(
    "content",
    [
        "---\ntype: Software Module\n---\n",
        "---\ntype: Custom Concept\nunknown: preserved\n---\n# Body\n",
        "---\ntype: Reference\ntitle: Example\ntags: [one, two]\n---\n",
        "---\r\ntype: Reference\r\n---\r\n",
    ],
)
def test_validate_readme_accepts_okf_without_optional_fields(content: str) -> None:
    assert validate_readme(content) is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "must begin"),
        ("# Module", "must begin"),
        ("\n---\ntype: Reference\n---\n", "must begin"),
        ("---\ntype: Reference\n", "missing closing"),
        ("---\ntype: [invalid\n---\n", "invalid YAML"),
        ("---\n---\n", "YAML mapping"),
        ("---\n- Reference\n---\n", "YAML mapping"),
        ("---\nReference\n---\n", "YAML mapping"),
        ("---\ntitle: Module\n---\n", "non-empty string type"),
        ("---\ntype: null\n---\n", "non-empty string type"),
        ("---\ntype: 12\n---\n", "non-empty string type"),
        ("---\ntype: false\n---\n", "non-empty string type"),
        ("---\ntype: []\n---\n", "non-empty string type"),
        ("---\ntype: '  '\n---\n", "non-empty string type"),
        ("---\ntype: !!python/object:unsafe {}\n---\n", "invalid YAML"),
    ],
)
def test_validate_readme_rejects_invalid_frontmatter(content: str, message: str) -> None:
    assert message in (validate_readme(content) or "")


def test_discovery_checks_all_src_trees_but_excludes_generated_and_landing_readmes(tmp_path: Path) -> None:
    included = ["app/src/README.md", "app/src/nested/README.md", "packages/sdk/src/module/README.md"]
    excluded = [
        "README.md",
        "app/README.md",
        "docs/README.md",
        "node_modules/vendor/src/README.md",
        "app/src/node_modules/vendor/README.md",
        "app/src/build/README.md",
        "app/.venv/vendor/src/README.md",
        "app/src/__pycache__/README.md",
    ]
    for relative in included + excluded:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not OKF", encoding="utf-8")
    assert set(find_module_readmes(tmp_path)) == {tmp_path / relative for relative in included}


def test_cli_reports_all_invalid_readmes_and_guidance(tmp_path: Path) -> None:
    for module in ("first", "second"):
        path = tmp_path / "src" / module / "README.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Not OKF", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "src/first/README.md" in result.stderr
    assert "src/second/README.md" in result.stderr
    assert "Follow OKF v0.2" in result.stderr
    assert "skills/development/write-module-readme/SKILL.md" in result.stderr


def test_cli_rejects_non_utf8_readme(tmp_path: Path) -> None:
    path = tmp_path / "src" / "README.md"
    path.parent.mkdir()
    path.write_bytes(b"\xff")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "src/README.md: cannot read UTF-8 Markdown" in result.stderr


def test_cli_rejects_empty_scan(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "No README.md files found beneath src directories" in result.stderr


def test_cli_rejects_missing_repository(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "missing")], capture_output=True, text=True)
    assert result.returncode != 0
    assert "repository is not a directory" in result.stderr


def test_cli_checks_repository_independently_of_working_directory(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, str(SCRIPT), str(repository)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OKF check passed" in result.stdout
