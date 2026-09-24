from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


SOURCE_DIRECTORIES: dict[str, str] = {
    "apps/umbod": "umbod",
    "apps/umbod-website": "website",
    "packages/umbod-connector-sdk": "packages/umbod-sdk",
}
SOURCE_FILES: dict[str, str] = {
    ".github/workflows/umbod-ci.yml": ".github/workflows/umbod-ci.yml",
    ".github/workflows/umbod-release.yml": ".github/workflows/umbod-release.yml",
    ".github/actions/docker-build/action.yml": ".github/actions/docker-build/action.yml",
    ".dockerignore": ".dockerignore",
}


def replace(path: Path, old: str, new: str) -> None:
    content = path.read_text()
    if old not in content:
        raise ValueError(f"Expected text not found in {path}: {old[:80]}")
    path.write_text(content.replace(old, new))


def remove_section(path: Path, start: str, end: str) -> None:
    content = path.read_text()
    if content.count(start) != 1 or end not in content.split(start, 1)[1]:
        raise ValueError(f"Cannot identify section in {path}: {start}")
    before, remainder = content.split(start, 1)
    _, after = remainder.split(end, 1)
    path.write_text(before + end + after)


def copy_tracked(source: Path, destination: Path) -> None:
    tracked = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z", "--", *SOURCE_DIRECTORIES, *SOURCE_FILES],
        check=True,
        capture_output=True,
    ).stdout
    paths = [os.fsdecode(item) for item in tracked.split(b"\0") if item]
    expected = set(SOURCE_FILES)
    if not expected.issubset(paths) or not all(
        any(path.startswith(f"{directory}/") for path in paths) for directory in SOURCE_DIRECTORIES
    ):
        raise ValueError("Required tracked sources are missing")
    for name in paths:
        if name == "apps/umbod/docker-compose.production.yml" or name == "apps/umbod/api/tests/deployment/test_plugin_volume_compose.py":
            continue
        target_name = SOURCE_FILES.get(name)
        if target_name is None:
            root = next(root for root in SOURCE_DIRECTORIES if name.startswith(f"{root}/"))
            target_name = SOURCE_DIRECTORIES[root] + name[len(root):]
        origin = source / name
        if name in (".github/workflows/umbod-ci.yml", ".github/workflows/umbod-release.yml") and not origin.is_file():
            origin = origin.with_suffix(".yml.disabled")
        target = destination / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_symlink():
            target.symlink_to(os.readlink(origin))
        elif origin.is_file():
            shutil.copy2(origin, target, follow_symlinks=False)
        else:
            raise ValueError(f"Tracked source is unavailable: {origin}")


def adapt(destination: Path) -> None:
    api = destination / "umbod/api"
    replace(api / "Dockerfile", "apps/umbod/api", "umbod/api")
    replace(api / "Dockerfile", "packages/umbod-connector-sdk", "packages/umbod-sdk")
    replace(destination / "packages/umbod-sdk/Dockerfile", "packages/umbod-connector-sdk", "packages/umbod-sdk")
    for name in ("pyproject.toml", "uv.lock"):
        replace(api / name, "../../../packages/umbod-connector-sdk", "../../packages/umbod-sdk")
    replace(destination / "website/package.json", "../umbod-website/public/docs", "../website/public/docs")

    compose = destination / "umbod/docker-compose.yml"
    remove_section(compose, "services:\n  plugin-init:\n", "  api:\n")
    compose.write_text("services:\n" + compose.read_text())
    replace(compose, "context: ../..", "context: ..")
    replace(compose, "dockerfile: apps/umbod/api/Dockerfile", "dockerfile: umbod/api/Dockerfile")
    replace(compose, "    depends_on:\n      plugin-init:\n        condition: service_completed_successfully\n", "")
    replace(compose, "      api:\n        condition: service_healthy\n", "    depends_on:\n      api:\n        condition: service_healthy\n")
    replace(compose, "      - PYTHONPATH=/plugins\n", "")
    replace(compose, "      - umbod-plugins:/plugins:ro\n", "")
    replace(compose, "  umbod-plugins:\n", "")
    replace(compose, '"connectors": [\n          {\n            "id": "rejseplanen"\n          },\n          {\n            "id": "slack"\n          },\n          {\n            "id": "test"\n          }\n        ]', '"connectors": []')

    ci = destination / ".github/workflows/umbod-ci.yml"
    replace(ci, "apps/umbod/", "umbod/")
    replace(ci, "apps/umbod", "umbod")
    replace(ci, "packages/umbod-connector-sdk", "packages/umbod-sdk")
    replace(ci, "      - 'packages/umbod-connectors/**'\n", "")
    remove_section(ci, "  plugins:\n", "  frontend:\n")
    remove_section(ci, "  helm-kind-install:\n", "  ci-complete:\n")
    replace(ci, "    needs: [changes, docs, backend-tests, core, connector-builder, frontend, plugins, helm, helm-kubernetes-schema, helm-kind-install]", "    needs: [changes, docs, backend-tests, core, connector-builder, frontend, helm, helm-kubernetes-schema]")
    replace(ci, "             [ \"${{ needs.plugins.result }}\" != \"success\" ] || \\\n", "")
    replace(ci, "             [ \"${{ needs.helm-kubernetes-schema.result }}\" != \"success\" ] || \\\n             { [ \"${{ needs.helm-kind-install.result }}\" != \"success\" ] && \\\n               [ \"${{ needs.helm-kind-install.result }}\" != \"skipped\" ]; }; then", "             [ \"${{ needs.helm-kubernetes-schema.result }}\" != \"success\" ]; then")

    release = destination / ".github/workflows/umbod-release.yml"
    replace(release, "apps/umbod/", "umbod/")
    replace(release, "packages/umbod-connector-sdk", "packages/umbod-sdk")
    replace(release, "Publish all four Umbod images", "Publish Umbod builder, core and frontend images")
    replace(release, "  PLUGINS_IMAGE: ghcr.io/computerlovetech/umbod-plugins\n", "")
    replace(release, "          plugins_tags=\"\"\n", "")
    replace(release, "            plugins_tags=\"$(package_tags umbod-plugins)\"\n", "")
    replace(release, "          plugins_latest=\"$(printf '%s\\n' \"${plugins_tags}\" | latest_version)\"\n", "")
    replace(release, ' || "${core_latest}" != "${plugins_latest}"', "")
    replace(release, ", plugins=${plugins_latest}", "")
    replace(release, ' | comm -12 - <(printf \'%s\\n\' "${plugins_tags}" | sort -u)', "")
    replace(release, ' "${PLUGINS_IMAGE}"', "")
    replace(release, "          - {name: plugins, image: ghcr.io/computerlovetech/umbod-plugins, context: ., file: packages/umbod-connectors/Dockerfile, cache: umbod-plugins-release}\n", "")
    replace(release, "Chart-only release requires a complete published image set", "Chart-only release requires published core, frontend and builder images")

    kind = destination / "umbod/deploy/helm/umbod/scripts/kind-install-test.sh"
    kind.unlink()
    plugin_validation = destination / "umbod/scripts/validate-plugin-images.sh"
    if plugin_validation.exists():
        plugin_validation.unlink()


def validate(destination: Path) -> None:
    required = ("umbod/api/Dockerfile", "umbod/docker-compose.yml", "umbod/api/uv.lock", "website/package.json", "packages/umbod-sdk/Dockerfile", ".github/workflows/umbod-ci.yml", ".github/workflows/umbod-release.yml", ".github/actions/docker-build/action.yml")
    if any(not (destination / path).is_file() for path in required):
        raise ValueError("Migration is missing a required file")
    if any((destination / path).exists() for path in ("umbod/docker-compose.production.yml", "packages/umbod-connectors", "umbod/api/tests/deployment/test_plugin_volume_compose.py")):
        raise ValueError("Migration included internal deployment artifacts")
    for path in (destination / ".github/workflows").glob("*.yml"):
        if "umbod-connectors" in path.read_text() or "umbod-plugins" in path.read_text() or "needs.plugins" in path.read_text():
            raise ValueError(f"Internal plugin image referenced in {path}")
    if "plugin-init" in (destination / "umbod/docker-compose.yml").read_text():
        raise ValueError("Local compose still requires plugin initialization")


def migrate(source: Path, destination: Path) -> None:
    if not (source / ".git").exists() or not destination.is_dir() or not (destination / ".git").exists():
        raise ValueError("Source and destination must be existing git repositories")
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must differ")
    if any(path.name not in {".git", "migrate_from_clt.py"} for path in destination.iterdir()):
        raise ValueError("Destination must be empty except for .git; refusing to overwrite or resume partial migration")
    workflows = [source / name for name in (".github/workflows/umbod-ci.yml", ".github/workflows/umbod-release.yml")]
    states = [(path.is_file(), path.with_suffix(".yml.disabled").is_file()) for path in workflows]
    if states not in ([(True, False), (True, False)], [(False, True), (False, True)]):
        raise ValueError("Source workflows must both be active or both be disabled")
    active_workflows = states[0][0]
    with tempfile.TemporaryDirectory(prefix="umbod-migration-", dir=destination.parent) as temporary:
        staged = Path(temporary)
        copy_tracked(source, staged)
        adapt(staged)
        validate(staged)
        moved: list[Path] = []
        disabled: list[Path] = []
        try:
            for item in staged.iterdir():
                target = destination / item.name
                item.rename(target)
                moved.append(target)
            validate(destination)
            if active_workflows:
                for workflow in workflows:
                    workflow.rename(workflow.with_suffix(".yml.disabled"))
                    disabled.append(workflow)
        except Exception:
            for workflow in reversed(disabled):
                workflow.with_suffix(".yml.disabled").rename(workflow)
            for item in reversed(moved):
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent / "clt")
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent)
    arguments = parser.parse_args()
    migrate(arguments.source, arguments.destination)


if __name__ == "__main__":
    main()
