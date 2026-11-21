from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from umbod.core.connectors.downstream_mcp.personal_oauth_metadata.models import MetadataEndpoint


def _validate_concrete_endpoint(value: str) -> str:
    if any(character in value for character in "{}\\#") or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ValueError("Registry endpoint must be a concrete HTTPS URL")
    return value


RegistryEndpointUrl = Annotated[
    MetadataEndpoint, AfterValidator(_validate_concrete_endpoint)
]
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegistrySearch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    term: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=256)
    ]
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, StringConstraints(max_length=2048)] = ""


class RegistryEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: RegistryEndpointUrl
    required_headers: tuple[NonBlankText, ...]


class RegistryServer(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: NonBlankText
    title: NonBlankText
    description: str
    version: NonBlankText
    endpoints: Annotated[tuple[RegistryEndpoint, ...], Field(min_length=1)]


class RegistryPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    servers: tuple[RegistryServer, ...]
    next_cursor: Annotated[str, StringConstraints(max_length=2048)]
