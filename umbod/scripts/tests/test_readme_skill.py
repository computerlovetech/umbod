import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[3] / "skills" / "development" / "write-module-readme"
CHECKERS = ["check_module_readmes.py", "check_readme_bodies.py", "check_readme_links.py"]


@pytest.mark.parametrize("checker", CHECKERS)
def test_skill_checks_run_from_an_arbitrary_installation_directory(tmp_path: Path, checker: str) -> None:
    installed = tmp_path / "installed-skill"
    shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
    repository = tmp_path / "target-repository"
    source = repository / "src"
    source.mkdir(parents=True)
    (source / "module.py").write_text("")
    (source / "README.md").write_text(
        "---\ntype: Software Module\n---\n\n# Files\n\n- [module](module.py) — Module implementation.\n"
    )
    result = subprocess.run(
        [sys.executable, str(installed / "scripts" / checker), str(repository)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "passed for 1" in result.stdout


@pytest.mark.parametrize("checker", CHECKERS)
def test_skill_checks_require_an_explicit_repository_root(tmp_path: Path, checker: str) -> None:
    result = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / checker)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "required: repository" in result.stderr
