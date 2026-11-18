from importlib import import_module
from typing import Any

__all__ = [
    "FilesystemSearchSharingRecipientsTool",
    "FilesystemShareTool",
    "SEARCH_RECIPIENTS_COMMAND",
    "SHARE_COMMAND",
]

_EXPORTS: dict[str, str] = {
    "FilesystemSearchSharingRecipientsTool": ".tools",
    "FilesystemShareTool": ".tools",
    "SEARCH_RECIPIENTS_COMMAND": ".models",
    "SHARE_COMMAND": ".models",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
