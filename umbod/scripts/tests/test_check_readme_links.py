import subprocess
import sys
from pathlib import Path

import pytest
from check_readme_links import find_readmes, local_destinations


SCRIPT = Path(__file__).resolve().parents[3] / "skills" / "development" / "write-module-readme" / "scripts" / "check_readme_links.py"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[module](src/module.py#entry)", ["src/module.py"]),
        ('[module](src/module.py?raw=1 "Title")', ["src/module.py"]),
        ("![image](assets/logo.png)", ["assets/logo.png"]),
        ("[module][ref]\n\n[ref]: src/module.py", ["src/module.py"]),
        ("[module][]\n\n[module]: src/module.py", ["src/module.py"]),
        ("[module]\n\n[module]: src/module.py", ["src/module.py"]),
        ("[file](<some file.md>)", ["some file.md"]),
        ("[file](some%20file.md)", ["some file.md"]),
        ("[file](folder/file_(one).md)", ["folder/file_(one).md"]),
        ('<a href="docs/file.md">File</a><img src="assets/logo.png">', ["assets/logo.png", "docs/file.md"]),
        ("[site](https://example.com) [mail](mailto:a@example.com) [cdn](//example.com/a)", []),
        ("[anchor](#heading) [query](?raw=1)", []),
        ("`[code](missing.md)`\n\n```md\n[code](missing.md)\n```", []),
        ("<!-- [hidden](missing.md) -->", []),
    ],
)
def test_extracts_only_local_link_destinations(content: str, expected: list[str]) -> None:
    assert local_destinations(content) == expected


def test_discovery_includes_root_and_nested_readmes_but_not_dependencies(tmp_path: Path) -> None:
    for relative in ["README.md", "docs/README.md", "node_modules/package/README.md", ".git/README.md"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    assert set(find_readmes(tmp_path)) == {tmp_path / "README.md", tmp_path / "docs/README.md"}


def test_cli_resolves_relative_and_root_paths_and_accepts_directories(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "file with spaces.md").write_text("")
    (docs / "README.md").write_text(
        "[relative](../file%20with%20spaces.md#heading) [root](/file%20with%20spaces.md) [dir](../docs/)"
    )
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], cwd=docs, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "passed for 1 README.md" in result.stdout


def test_cli_reports_all_missing_targets_and_fails(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[first](missing.md) ![second](missing.png)")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "README.md: missing local target: missing.md" in result.stderr
    assert "README.md: missing local target: missing.png" in result.stderr


def test_cli_rejects_unreadable_markdown(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "cannot check links" in result.stderr


def test_cli_rejects_empty_scan(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "No README.md files found" in result.stderr
