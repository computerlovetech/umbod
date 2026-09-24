import shutil
from enum import Enum
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory


class Harness(str, Enum):
    claude = "claude"
    codex = "codex"
    agents = "agents"


class Scope(str, Enum):
    project = "project"
    user = "user"


def bundled_skills() -> list[str]:
    root = files("umbod_sdk").joinpath("skills")
    return sorted(item.name for item in root.iterdir() if item.is_dir() and item.joinpath("SKILL.md").is_file())


def skills_directory(harness: Harness, scope: Scope, project: Path | None = None) -> Path:
    base = (project if project is not None else Path.cwd()) if scope is Scope.project else Path.home()
    folder = ".claude" if harness is Harness.claude else ".agents"
    return base / folder / "skills"


def install_skills(names: list[str], destination: Path, force: bool = False) -> list[Path]:
    available = set(bundled_skills())
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(f"Unknown skill: {', '.join(unknown)}")

    targets = [destination / name for name in names]
    for target in targets:
        if target.is_symlink():
            raise ValueError(f"Refusing to replace a symlink: {target}")
        if (target.exists() or target.is_symlink()) and not force:
            raise ValueError(f"Skill already exists: {target} (use --force to replace it)")
        if target.exists() and not target.is_dir():
            raise ValueError(f"Skill destination is not a directory: {target}")

    destination.mkdir(parents=True, exist_ok=True)
    resources = files("umbod_sdk").joinpath("skills")
    for name, target in zip(names, targets):
        with TemporaryDirectory(dir=destination) as staging:
            staged = Path(staging) / name
            with as_file(resources.joinpath(name)) as source:
                shutil.copytree(source, staged)
            if target.exists():
                shutil.rmtree(target)
            staged.rename(target)
    return targets
