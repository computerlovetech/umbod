from importlib import import_module
from typing import Any

__all__ = [
    "BeginUploadCommand",
    "FilesystemBeginUploadTool",
    "FilesystemCompleteUploadTool",
    "FilesystemUploadTool",
    "UploadCommand",
]

_EXPORTS: dict[str, str] = {
    "BeginUploadCommand": ".session_models",
    "FilesystemBeginUploadTool": ".sessions",
    "FilesystemCompleteUploadTool": ".sessions",
    "FilesystemUploadTool": ".one_shot",
    "UploadCommand": ".one_shot_models",
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
