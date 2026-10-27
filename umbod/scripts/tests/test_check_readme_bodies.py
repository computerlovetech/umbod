import subprocess
import sys
from pathlib import Path

import pytest
from check_readme_bodies import validate_body


SCRIPT = Path(__file__).resolve().parents[3] / "skills" / "development" / "write-module-readme" / "scripts" / "check_readme_bodies.py"
FRONTMATTER = "---\ntype: Software Module\n---\n"


@pytest.mark.parametrize(
    "body",
    [
        "# Files\n\n- [module](module.py) — Short description.\n",
        "## Files\n\n* [module](module.py) Short description.\n",
        "Files\n=====\n\n- [`module`](module.py) — Uses `inline code` and **emphasis**.\n",
        "# Files\n\n- [module][ref] — Short description.\n\n[ref]: module.py\n",
        "# Files\n\n- [module](module.py) — A wrapped\n  description.\n",
        "# Files\n\n- [module](module.py) — " + "x" * 160,
        "# Context not available from the code\n\n- [decision](adr.md) — Short relevance cue.\n",
        "# Files\n\n- [one](one.py) — First.\n\n- [two](two.py) — Second.\n",
        "- [parent](parent.py) — Parent.\n  - [child](child.py) — Child.",
        "",
    ],
)
def test_accepts_headings_and_linked_bullets(body: str) -> None:
    assert validate_body(FRONTMATTER + body) == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("Standalone paragraph.", "only headings"),
        ("```python\npass\n```", "only headings"),
        ("    pass", "only headings"),
        ("| File | Purpose |\n| --- | --- |\n| a | b |", "only headings"),
        ("<div>HTML</div>", "only headings"),
        ("<!-- hidden prose -->", "only headings"),
        ("> Quoted prose", "only headings"),
        ("1. [module](module.py) — Description.", "only headings"),
        ("- [module](module.py) — Description.\n\n  Extra paragraph.", "only headings"),
        ("- Text without a link.", "must start"),
        ("- Text [module](module.py) — Description.", "must start"),
        ("- ![image](image.png) — Description.", "must start"),
        ("- [module](module.py)", "short description"),
        ("- [module](module.py) —", "non-empty description"),
        ("- [](module.py) — Description.", "non-empty text label"),
        ("- [module](module.py) — See [other](other.py).", "only text"),
        ("- [module](module.py) — <b>HTML</b>.", "only text"),
        ("- [module](module.py) — " + "x" * 161, "exceeds 160"),
    ],
)
def test_rejects_content_outside_strict_body_format(body: str, message: str) -> None:
    assert any(message in issue for issue in validate_body(FRONTMATTER + body))


def test_reports_original_line_numbers() -> None:
    assert validate_body(FRONTMATTER + "\n# Files\n\nProse.")[0].startswith("line 7:")


def test_rejects_invalid_frontmatter() -> None:
    assert "must begin with YAML" in validate_body("# Files")[0]


def test_cli_reports_failures_in_all_modules_and_excludes_landing_readmes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Landing page prose.")
    for name in ["first", "second"]:
        readme = tmp_path / "src" / name / "README.md"
        readme.parent.mkdir(parents=True)
        readme.write_text(FRONTMATTER + "Standalone prose.")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "src/first/README.md: line 4:" in result.stderr
    assert "src/second/README.md: line 4:" in result.stderr
    assert "Landing" not in result.stderr


def test_cli_passes_valid_repository_from_different_working_directory(tmp_path: Path) -> None:
    readme = tmp_path / "src" / "README.md"
    readme.parent.mkdir()
    readme.write_text(FRONTMATTER + "# Files\n\n- [module](module.py) — Description.")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], cwd=readme.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "passed for 1 module READMEs" in result.stdout


@pytest.mark.parametrize("invalid_utf8", [False, True])
def test_cli_fails_for_empty_scan_or_invalid_utf8(tmp_path: Path, invalid_utf8: bool) -> None:
    if invalid_utf8:
        readme = tmp_path / "src" / "README.md"
        readme.parent.mkdir()
        readme.write_bytes(b"\xff")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert ("cannot read UTF-8" if invalid_utf8 else "No README.md files found") in result.stderr


def test_cli_rejects_missing_repository(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "missing")], capture_output=True, text=True)
    assert result.returncode != 0
    assert "repository is not a directory" in result.stderr
