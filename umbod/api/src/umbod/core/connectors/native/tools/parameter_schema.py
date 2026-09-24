from typing import Literal

from pydantic import ConfigDict, Field
from umbod.proxies import Model

from umbod.core.connectors.native.tools.descriptions import ConnectorToolParameterDescription


class ToolParameterPropertySchema(Model):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "integer", "number", "boolean"]
    description: str


class ToolParameterObjectSchema(Model):
    model_config = ConfigDict(extra="forbid")

    type: Literal["object"] = "object"
    properties: dict[str, ToolParameterPropertySchema]
    required: list[str] = Field(default_factory=list)

    @classmethod
    def from_descriptions(
        cls, parameters: list[ConnectorToolParameterDescription]
    ) -> "ToolParameterObjectSchema":
        return cls(
            properties={
                parameter.name: ToolParameterPropertySchema(
                    type=parameter.type,
                    description=parameter.description,
                )
                for parameter in parameters
            },
            required=[parameter.name for parameter in parameters if parameter.required],
        )
