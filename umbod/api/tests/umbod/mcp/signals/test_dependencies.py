import ast
from importlib import import_module
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("statement", (
    "from umbod.mcp.signals import McpInvocationPublisher",
    "from umbod.mcp.signals import SignalToolExecutionPipelineFactory",
    "from umbod.mcp.listeners import create_mcp_signals",
    "from umbod.mcp.tools import McpObservedToolRegistrar",
))
def test_signal_public_interfaces_import_without_ordering_dependencies(statement: str) -> None:
    result = subprocess.run([sys.executable, "-c", statement], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module_path", (
    "logging/invocation/event.py",
    "logging/invocation/context.py",
    "logging/invocation/recorder.py",
    "tools/invocation/__init__.py",
    "tools/invocation/lifecycle.py",
    "tools/invocation/diagnostics.py",
    "tools/invocation/telemetry.py",
    "connectors/native/tools/invocation/lifecycle.py",
    "connectors/native/tools/invocation/telemetry.py",
    "connectors/openapi/metrics.py",
))
def test_removed_invocation_implementations_and_compatibility_paths_are_absent(module_path: str) -> None:
    source_root = Path(__file__).resolve().parents[4] / "src" / "umbod" / "mcp"
    assert not (source_root / module_path).exists()


@pytest.mark.parametrize("package_name", ("umbod.mcp.logging", "umbod.mcp.logging.invocation"))
def test_logging_packages_do_not_reexport_neutral_events_or_legacy_loggers(package_name: str) -> None:
    package = import_module(package_name)
    removed = (
        "ConnectorToolInvocationLogger", "CompositeConnectorToolInvocationLogger",
        "InvocationLogSinkToolInvocationLogger", "AuditToolInvocationLogger",
        "create_default_connector_tool_invocation_logger", "McpToolIdentity",
        "McpToolInvocationCompleted", "McpInvocationContext", "McpInvocationActor",
        "current_mcp_invocation_context", "set_mcp_invocation_context",
    )
    assert all(not hasattr(package, name) for name in removed)


def test_source_imports_use_only_canonical_invocation_modules() -> None:
    source_root = Path(__file__).resolve().parents[4] / "src"
    removed = (
        "umbod.mcp.logging.invocation.event",
        "umbod.mcp.logging.invocation.context",
        "umbod.mcp.logging.invocation.recorder",
        "umbod.mcp.tools.invocation",
        "umbod.mcp.connectors.native.tools.invocation.lifecycle",
        "umbod.mcp.connectors.native.tools.invocation.telemetry",
        "umbod.mcp.connectors.openapi.metrics",
    )
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = (
                [node.module or ""] if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names] if isinstance(node, ast.Import)
                else []
            )
            for module in modules:
                if any(module == name or module.startswith(name + ".") for name in removed):
                    violations.append(f"{path.relative_to(source_root)}:{node.lineno}: {module}")
    assert violations == []


CONCRETE_MODULES = (
    "connectors/native/tools/registration.py",
    "connectors/native/tools/runtime/registry.py",
    "connectors/native/tools/invocation/identity.py",
    "connectors/downstream_mcp/provider.py",
    "connectors/downstream_mcp/tool_invocation.py",
    "connectors/downstream_mcp/inventory.py",
    "connectors/openapi/codemode_execution.py",
    "connectors/openapi/inventory.py",
    "tools/registration.py",
)


@pytest.mark.parametrize("module_path", CONCRETE_MODULES)
def test_concrete_tool_modules_do_not_depend_on_side_effect_implementations(module_path: str) -> None:
    source_root = Path(__file__).resolve().parents[4] / "src" / "umbod" / "mcp"
    tree = ast.parse((source_root / module_path).read_text())
    imports = {
        name
        for node in ast.walk(tree)
        for name in (
            [node.module or ""] if isinstance(node, ast.ImportFrom)
            else [alias.name for alias in node.names] if isinstance(node, ast.Import)
            else []
        )
    }
    forbidden = {
        name for name in imports
        if name.startswith(("umbod.mcp.metrics", "umbod.mcp.logging", "umbod.mcp.listeners"))
        or "telemetry" in name.split(".")
    }
    assert forbidden == set()
    definitions = (
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    assert all("telemetry" not in name.lower() and "metrics" not in name.lower() for name in definitions)
