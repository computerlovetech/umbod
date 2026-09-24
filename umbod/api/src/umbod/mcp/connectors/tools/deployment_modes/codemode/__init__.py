from importlib import import_module
from typing import Any

from umbod.mcp.connectors.tools.deployment_modes.codemode.sandbox import (
    OpenApiCodeModeExecutor,
    OpenApiCodeModeInvocation,
)

__all__ = [
    "CodeModeConnectorToolDeploymentFactory",
    "OpenApiCodeModeExecutor",
    "OpenApiCodeModeInvocation",
]


def __getattr__(name: str) -> Any:
    if name == "CodeModeConnectorToolDeploymentFactory":
        value = getattr(
            import_module(
                "umbod.mcp.connectors.tools.deployment_modes.codemode.deployment"
            ),
            name,
        )
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
