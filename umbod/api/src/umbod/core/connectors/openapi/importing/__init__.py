from importlib import import_module
from typing import Any

__all__ = [
    "DefaultOpenApiImportPreparer",
    "InMemoryOpenApiCandidateImporter",
    "JsonDocumentDecodeError",
    "JsonDocumentErrorCode",
    "JsonPointerResolutionError",
    "Location",
    "OpenApiCandidateImporter",
    "OpenApiImportPreparer",
    "OpenApiSchemaParser",
    "OpenApiServerSelectionRequired",
    "PreparedOpenApiImport",
    "SameDocumentJsonPointerResolver",
    "ValidationIssues",
    "decode_json_object",
]

_EXPORTS: dict[str, str] = {
    "DefaultOpenApiImportPreparer": ".preparation",
    "InMemoryOpenApiCandidateImporter": ".importer",
    "JsonDocumentDecodeError": ".json_document",
    "JsonDocumentErrorCode": ".json_document",
    "JsonPointerResolutionError": ".json_pointer",
    "Location": ".parsing",
    "OpenApiCandidateImporter": ".ports",
    "OpenApiImportPreparer": ".preparation",
    "OpenApiSchemaParser": ".schema_parser",
    "OpenApiServerSelectionRequired": ".preparation",
    "PreparedOpenApiImport": ".preparation",
    "SameDocumentJsonPointerResolver": ".json_pointer",
    "ValidationIssues": ".parsing",
    "decode_json_object": ".json_document",
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
