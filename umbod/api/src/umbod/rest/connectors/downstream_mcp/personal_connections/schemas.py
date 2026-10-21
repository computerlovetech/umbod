from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorSelection


class PersonalEnablementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class PersonalConnectorResponse(PersonalConnectorSelection):
    runtime_available: Literal[False]
    runtime_unavailable_reason: Literal["personal_oauth_not_supported"]


class PersonalConnectorListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connectors: tuple[PersonalConnectorResponse, ...]


def present_personal_connector(selection: PersonalConnectorSelection) -> PersonalConnectorResponse:
    return PersonalConnectorResponse(
        **selection.model_dump(),
        runtime_available=False,
        runtime_unavailable_reason="personal_oauth_not_supported",
    )
