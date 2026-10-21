from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorSelection


class PersonalEnablementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class PersonalConnectorResponse(PersonalConnectorSelection):
    runtime_available: bool
    runtime_unavailable_reason: Literal["", "personal_oauth_not_supported"]


class PersonalConnectorListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connectors: tuple[PersonalConnectorResponse, ...]


def present_personal_connector(selection: PersonalConnectorSelection, available_connector_ids: frozenset[str]) -> PersonalConnectorResponse:
    return PersonalConnectorResponse(
        **selection.model_dump(),
        runtime_available=selection.connector_id in available_connector_ids,
        runtime_unavailable_reason="" if selection.connector_id in available_connector_ids else "personal_oauth_not_supported",
    )
