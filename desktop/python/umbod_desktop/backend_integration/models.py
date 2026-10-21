from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from umbod.core.connectors.downstream_mcp.models import EndpointUrl


class DesktopServer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    host_id: str = ""
    name: str = Field(min_length=1, max_length=200)
    transport: Literal["stdio", "http"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    oauth: bool = False
    oauth_scopes: str = ""
    reconnect: bool = Field(default=False, exclude=True)
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_transport(self) -> Self:
        if self.transport == "stdio" and not self.command.strip():
            raise ValueError("A local executable is required")
        if self.transport == "http":
            TypeAdapter(EndpointUrl).validate_python(self.url)
        if any(
            not reference.startswith("upstream:")
            for reference in (*self.headers.values(), *self.env.values())
        ):
            raise ValueError("Credentials must be upstream Keychain references")
        return self


