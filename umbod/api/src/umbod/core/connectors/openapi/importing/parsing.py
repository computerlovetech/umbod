from collections.abc import Mapping, Sequence
from typing import TypeAlias

from umbod.core.connectors.openapi.errors import OpenApiValidationIssue

Location: TypeAlias = tuple[str | int, ...]


class ValidationIssues:
    def __init__(self) -> None:
        self.values: list[OpenApiValidationIssue] = []

    def add(self, code: str, location: Location, message: str) -> None:
        self.values.append(OpenApiValidationIssue(code=code, location=location, message=message))

    def reject_reference(self, value: object, location: Location) -> bool:
        if isinstance(value, Mapping) and "$ref" in value:
            self.add("unsupported_reference", (*location, "$ref"), "References are unsupported")
            return True
        return False

    def reject_references(self, value: object, location: Location) -> bool:
        found = False
        if isinstance(value, Mapping):
            for key, nested in value.items():
                nested_location = (*location, key) if isinstance(key, (str, int)) else location
                if key == "$ref":
                    self.add("unsupported_reference", nested_location, "References are unsupported")
                    found = True
                elif self.reject_references(nested, nested_location):
                    found = True
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, nested in enumerate(value):
                if self.reject_references(nested, (*location, index)):
                    found = True
        return found
