from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .validation import validated_url


class OAuthDestination(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    url: str


class NoOAuthHttpAuthentication(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["none"] = "none"


class BasicOAuthHttpAuthentication(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["basic"] = "basic"
    client_id: SecretStr
    client_secret: SecretStr


OAuthHttpAuthentication = Annotated[
    NoOAuthHttpAuthentication | BasicOAuthHttpAuthentication, Field(discriminator="kind")
]


class OAuthHttpRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    method: Literal["GET", "POST"]
    url: str
    content_type: str
    body: SecretStr
    authentication: OAuthHttpAuthentication = Field(default_factory=NoOAuthHttpAuthentication)


class OAuthHttpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: int
    body: bytes = Field(repr=False)


class OAuthHttpTransport(Protocol):
    async def validate_destination(self, command: OAuthDestination) -> None: ...

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse: ...


class InMemoryOAuthHttpTransport:
    def __init__(self, responses: list[OAuthHttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[OAuthHttpRequest] = []
        self.destinations: list[OAuthDestination] = []

    async def validate_destination(self, command: OAuthDestination) -> None:
        validated_url(command.url)
        self.destinations.append(command)

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(command)
        return self.responses.pop(0)
