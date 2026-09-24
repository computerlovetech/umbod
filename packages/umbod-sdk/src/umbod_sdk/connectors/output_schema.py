from dataclasses import dataclass
from typing import Any, Literal, TypeAlias


@dataclass(frozen=True)
class AbsentConnectorToolOutputSchema:
    output_schema_status: Literal["absent"] = "absent"


@dataclass(frozen=True)
class PresentConnectorToolOutputSchema:
    output_schema: dict[str, Any]
    output_schema_status: Literal["present"] = "present"


ConnectorToolOutputSchema: TypeAlias = (
    AbsentConnectorToolOutputSchema | PresentConnectorToolOutputSchema
)

__all__ = [
    "AbsentConnectorToolOutputSchema",
    "ConnectorToolOutputSchema",
    "PresentConnectorToolOutputSchema",
]
