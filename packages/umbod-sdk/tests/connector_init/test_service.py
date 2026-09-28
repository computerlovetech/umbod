import tomllib

import pytest

from umbod_sdk.connector_init import (
    ConnectorInitializer,
    InitError,
    InitRequest,
    InMemoryProjectFiles,
)

METADATA = b'''# preserve this comment\n[project]\nname = "sample"\ndependencies = ["umbod"]\n\n[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[tool.hatch.build.targets.wheel]\npackages = ["src/my_package"]\n'''
REQUEST = InitRequest(project_directory=".", name="my-connector", module="my_package.hello_world")


def test_preview_preserves_project_and_exposes_complete_changes() -> None:
    files = InMemoryProjectFiles(METADATA, "my_package")
    plan = ConnectorInitializer(files).plan(REQUEST)
    assert files.metadata == METADATA
    assert files.modules == {}
    assert plan.source.endswith("plugin = connector\n")
    assert plan.metadata_addition.endswith(b'my-connector = "my_package.hello_world:plugin"\n')


def test_apply_preserves_existing_metadata_bytes_and_creates_source() -> None:
    files = InMemoryProjectFiles(METADATA, "my_package")
    initializer = ConnectorInitializer(files)
    plan = initializer.plan(REQUEST)
    initializer.apply(plan)
    assert files.metadata == METADATA + plan.metadata_addition
    assert files.modules[REQUEST.module] == plan.source.encode()
    assert tomllib.loads(files.metadata.decode())["project"]["entry-points"]["umbod.connectors"] == {
        "my-connector": "my_package.hello_world:plugin"
    }


@pytest.mark.parametrize("name", ["My-connector", "my_connector", "my--connector", "", "1-my"])
def test_invalid_names_refused(name: str) -> None:
    with pytest.raises(InitError, match="--name"):
        ConnectorInitializer(InMemoryProjectFiles(METADATA, "my_package")).plan(
            REQUEST.model_copy(update={"name": name})
        )


@pytest.mark.parametrize("module", ["my_package", "my_package.a.b", "my_package.__init__", "my_package.class", "other.hello_world", "mypäckage.hello_world", "my_package.héllo"])
def test_invalid_module_or_missing_package_refused(module: str) -> None:
    with pytest.raises(InitError):
        ConnectorInitializer(InMemoryProjectFiles(METADATA, "my_package")).plan(
            REQUEST.model_copy(update={"module": module})
        )


@pytest.mark.parametrize("metadata", [
    b"not toml = [",
    b"\xff",
    b"[build-system]\nbuild-backend = 'hatchling.build'",
    METADATA.replace(b'hatchling.build', b'setuptools.build_meta'),
    METADATA.replace(b'[tool.hatch.build.targets.wheel]\npackages = ["src/my_package"]', b''),
    METADATA.replace(b'[project]\n', b'[project]\ndynamic = ["entry-points"]\n'),
    METADATA.replace(b'[project]\n', b'[project]\ndynamic = [1]\n'),
    METADATA.replace(b'packages = ["src/my_package"]', b'packages = ["src/my_package", 1]'),
    METADATA.replace(b'[project]\n', b'[project]\nentry-points = { other = "value" }\n'),
    METADATA + b'\n[project.entry-points."umbod.connectors"]\n',
    METADATA + b'\n[project.entry-points."umbod.connectors"]\nold = "x:y"\n',
])
def test_unsupported_metadata_refused(metadata: bytes) -> None:
    with pytest.raises(InitError):
        ConnectorInitializer(InMemoryProjectFiles(metadata, "my_package")).plan(REQUEST)


@pytest.mark.parametrize("path,replacement", [
    ("tool", b'tool = "scalar"\n'),
    ("tool.hatch", b'[tool]\nhatch = "scalar"\n'),
    ("tool.hatch.build", b'[tool.hatch]\nbuild = "scalar"\n'),
    ("tool.hatch.build.targets", b'[tool.hatch.build]\ntargets = "scalar"\n'),
    ("tool.hatch.build.targets.wheel", b'[tool.hatch.build.targets]\nwheel = "scalar"\n'),
])
def test_scalar_hatch_intermediate_reports_exact_path(path: str, replacement: bytes) -> None:
    base = METADATA.split(b"[tool.hatch.build.targets.wheel]")[0]
    metadata = replacement + base if path == "tool" else base + replacement
    with pytest.raises(InitError) as caught:
        ConnectorInitializer(InMemoryProjectFiles(metadata, "my_package")).plan(REQUEST)
    assert f"[{path}] must be a table" in str(caught.value)


def test_existing_module_and_package_refused() -> None:
    files = InMemoryProjectFiles(METADATA, "my_package")
    files.package_directories.add(REQUEST.module)
    with pytest.raises(InitError, match="already exists"):
        ConnectorInitializer(files).plan(REQUEST)


def test_changed_metadata_since_plan_is_not_overwritten() -> None:
    files = InMemoryProjectFiles(METADATA, "my_package")
    initializer = ConnectorInitializer(files)
    plan = initializer.plan(REQUEST)
    files.metadata += b"\n# concurrent edit\n"
    with pytest.raises(InitError, match="changed"):
        initializer.apply(plan)
    assert files.modules == {}
    assert files.metadata.endswith(b"# concurrent edit\n")


def test_metadata_write_failure_leaves_created_module_for_inspection() -> None:
    class FailingProjectFiles(InMemoryProjectFiles):
        def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None:
            raise PermissionError("write denied")

    files = FailingProjectFiles(METADATA, "my_package")
    initializer = ConnectorInitializer(files)
    with pytest.raises(InitError, match="No automatic cleanup"):
        initializer.apply(initializer.plan(REQUEST))
    assert files.modules[REQUEST.module].endswith(b"plugin = connector\n")
    assert files.metadata == METADATA


def test_metadata_failure_preserves_concurrent_module_replacement() -> None:
    class ReplacedFiles(InMemoryProjectFiles):
        def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None:
            self.modules[request.module] = b"replacement"
            raise PermissionError("write denied")

    files = ReplacedFiles(METADATA, "my_package")
    initializer = ConnectorInitializer(files)
    with pytest.raises(InitError, match="inspect"):
        initializer.apply(initializer.plan(REQUEST))
    assert files.modules[REQUEST.module] == b"replacement"


def test_collision_since_plan_is_not_overwritten() -> None:
    files = InMemoryProjectFiles(METADATA, "my_package")
    initializer = ConnectorInitializer(files)
    plan = initializer.plan(REQUEST)
    files.modules[REQUEST.module] = b"existing"
    with pytest.raises(InitError, match="already exists"):
        initializer.apply(plan)
    assert files.modules[REQUEST.module] == b"existing"
