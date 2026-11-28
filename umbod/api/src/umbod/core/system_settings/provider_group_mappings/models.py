from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictStr

from ..models import SettingsSource


def _validate_mapping_value(value: str) -> str:
    if not value.strip():
        raise ValueError("Mapping values must not be blank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Mapping values must be valid Unicode") from None
    return value


def is_mappable_group_id(group_id: str) -> bool:
    try:
        _validate_mapping_value(group_id)
    except ValueError:
        return False
    return True


type MappingValue = Annotated[StrictStr, AfterValidator(_validate_mapping_value)]


class ProviderGroupMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_value: MappingValue
    group_id: MappingValue


def _validate_mappings(
    mappings: tuple[ProviderGroupMapping, ...],
) -> tuple[ProviderGroupMapping, ...]:
    if len(set(mappings)) != len(mappings):
        raise ValueError("Duplicate provider group mappings")
    return mappings


type ProviderGroupMappings = Annotated[
    tuple[ProviderGroupMapping, ...], AfterValidator(_validate_mappings)
]


class EffectiveProviderGroupMappings(BaseModel):
    model_config = ConfigDict(frozen=True)

    mappings: ProviderGroupMappings
    source: SettingsSource | Literal["inherited_claim_default"]
