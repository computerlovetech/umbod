from pathlib import Path

import pytest
from pydantic_monty import MountDir

from umbod_sdk.connectors import declaration, http


@pytest.fixture
def sdk_mount(tmp_path: Path) -> MountDir:
    sdk_package = tmp_path / "umbod_sdk"
    connectors_package = sdk_package / "connectors"
    connectors_package.mkdir(parents=True)
    (sdk_package / "__init__.py").touch()
    (connectors_package / "__init__.py").write_text(Path(declaration.__file__).read_text())
    (connectors_package / "http.py").write_text(Path(http.__file__).read_text())
    return MountDir(host_path=tmp_path, virtual_path="/sdk", mode="read-only")
