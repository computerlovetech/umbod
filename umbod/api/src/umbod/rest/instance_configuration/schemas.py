from typing import Literal, Union

from pydantic import BaseModel


class InstanceConfigurationEntryResponse(BaseModel):
    variable: str
    label: str
    description: str
    type: Literal["string", "integer", "number", "boolean", "string_list"]
    value: Union[str, int, float, bool, list[str]]


class InstanceConfigurationGroupResponse(BaseModel):
    id: str
    label: str
    entries: list[InstanceConfigurationEntryResponse]


class InstanceConfigurationResponse(BaseModel):
    groups: list[InstanceConfigurationGroupResponse]
