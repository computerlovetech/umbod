from pydantic import BaseModel, ConfigDict, Field, StrictBool

from umbod.core.capabilities.descriptions import CapabilityDescription


class PersonalConnectorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str = Field(min_length=1)


class SetPersonalConnectorEnablement(PersonalConnectorQuery):
    enabled: StrictBool


class PersonalConnectorSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    display_name: str
    capability_description: CapabilityDescription
    enabled: bool
    has_authorization: bool


class PersonalConnectorSelections(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connectors: tuple[PersonalConnectorSelection, ...]


class PersonalConnectorUnavailable(LookupError):
    pass
