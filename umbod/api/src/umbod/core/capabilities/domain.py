from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import JsonValue

from umbod.core.invocation import ConnectorKind

JsonObject: TypeAlias = dict[str, JsonValue]
CapabilityKind = Literal["tool", "prompt", "resource", "resource_template"]


class CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)


class CapabilityIdentity(CapabilityModel):
    connector_kind: ConnectorKind
    connector_id: str = Field(min_length=1)
    capability_kind: CapabilityKind
    capability_key: str = Field(min_length=1)


class AbsentCapabilityOutputSchema(CapabilityModel):
    status: Literal["absent"] = "absent"


class PresentCapabilityOutputSchema(CapabilityModel):
    status: Literal["present"] = "present"
    schema_: JsonObject = Field(alias="schema", serialization_alias="schema")


CapabilityOutputSchema = Annotated[
    Union[AbsentCapabilityOutputSchema, PresentCapabilityOutputSchema],
    Field(discriminator="status"),
]


class NormalizedCapability(CapabilityModel):
    identity: CapabilityIdentity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: JsonObject
    output_schema: CapabilityOutputSchema
    connector_display_name: str = ""
    connector_capability_description: str = "Connector capabilities"
    search_hints: tuple[str, ...] = ()
