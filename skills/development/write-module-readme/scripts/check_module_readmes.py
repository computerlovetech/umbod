import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import yaml


EXCLUDED_DIRECTORIES = {
    ".agents",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def validate_readme(content: str) -> Optional[str]:
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        return "must begin with YAML frontmatter delimited by ---"
    try:
        closing_delimiter = lines.index("---", 1)
    except ValueError:
        return "missing closing --- frontmatter delimiter"
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing_delimiter]))
    except yaml.YAMLError:
        return "frontmatter contains invalid YAML"
    if not isinstance(metadata, dict):
        return "frontmatter must be a YAML mapping"
    concept_type = metadata.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        return "frontmatter must contain a non-empty string type"
    return None


def raise_walk_error(error: OSError) -> None:
    raise error


def find_module_readmes(repository: Path) -> List[Path]:
    readmes: List[Path] = []
    for directory, children, filenames in os.walk(repository, onerror=raise_walk_error):
        children[:] = sorted(set(children) - EXCLUDED_DIRECTORIES)
        path = Path(directory)
        if "src" in path.relative_to(repository).parts and "README.md" in filenames:
            readmes.append(path / "README.md")
    return readmes


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source module READMEs for OKF frontmatter.")
    parser.add_argument("repository", type=Path)
    repository = parser.parse_args().repository.resolve()
    if not repository.is_dir():
        parser.error(f"repository is not a directory: {repository}")
    try:
        readmes = find_module_readmes(repository)
    except OSError as error:
        sys.stderr.write(f"Cannot scan source directories: {error}\n")
        return 1
    failures: List[str] = []
    for path in readmes:
        try:
            issue = validate_readme(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as error:
            issue = f"cannot read UTF-8 Markdown: {error}"
        if issue:
            failures.append(f"{path.relative_to(repository)}: {issue}")
    if not readmes:
        failures.append("No README.md files found beneath src directories; check the repository path.")
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        sys.stderr.write("Follow OKF v0.2 and skills/development/write-module-readme/SKILL.md.\n")
        return 1
    sys.stdout.write(f"OKF check passed for {len(readmes)} module READMEs.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
