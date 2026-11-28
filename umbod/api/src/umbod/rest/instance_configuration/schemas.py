from typing import Literal, Union

from umbod.proxies import Model


class InstanceConfigurationEntryResponse(Model):
    variable: str
    label: str
    description: str
    type: Literal["string", "integer", "number", "boolean", "string_list"]
    value: Union[str, int, float, bool, list[str]]


class InstanceConfigurationGroupResponse(Model):
    id: str
    label: str
    entries: list[InstanceConfigurationEntryResponse]


class InstanceConfigurationResponse(Model):
    groups: list[InstanceConfigurationGroupResponse]
