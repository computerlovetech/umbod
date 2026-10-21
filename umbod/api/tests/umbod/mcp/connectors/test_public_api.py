import importlib
import subprocess
import sys
from types import ModuleType

import pytest

from umbod.mcp import connectors


def test_public_api_exposes_only_connector_kind_namespaces() -> None:
    assert set(connectors.__all__) == {"downstream_mcp", "native", "openapi"}
    assert set(connectors.__all__).issubset(dir(connectors))


@pytest.mark.parametrize("name", ["downstream_mcp", "native", "openapi"])
def test_public_namespace_resolves_to_its_connector_package(name: str) -> None:
    namespace = getattr(connectors, name)

    assert isinstance(namespace, ModuleType)
    assert namespace is importlib.import_module(f"umbod.mcp.connectors.{name}")
    assert getattr(connectors, name) is namespace


@pytest.mark.parametrize(
    "name",
    ["register_connector_tools", "ApprovalStateCodec", "_arguments_without_file_data"],
)
def test_kind_specific_objects_are_not_promoted_to_root_api(name: str) -> None:
    with pytest.raises(AttributeError, match=name):
        getattr(connectors, name)


def test_importing_connector_api_does_not_load_connector_implementations() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import umbod.mcp.connectors as connectors; "
            "assert connectors.__all__ == ['downstream_mcp', 'native', 'openapi']; "
            "assert not any(name.startswith('umbod.mcp.connectors.') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
