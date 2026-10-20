from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

DESKTOP_GROUP = "desktop-owner"


class DesktopContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConnectorDefinition(DesktopContract):
    connector_id: str
    display_name: str
    tool_name_prefix: str
    public_path: str


class ProxyConfiguration(DesktopContract):
    auth_mode: Literal["static_bearer"]
    endpoint_url: str
    header_type: Literal["bearer"]
    bearer_token: str = Field(repr=False)


class ConnectorCreation(DesktopContract):
    display_name: str
    tool_name_prefix: str
    public_path: str
    capability_description: str
    configuration: ProxyConfiguration


class ToolSelection(DesktopContract):
    connector_id: str
    names: tuple[str, ...]


class ToolGrant(DesktopContract):
    group_id: str
    selection: ToolSelection


class UpstreamInput(RootModel[dict[str, Any]]):
    model_config = ConfigDict(frozen=True)


class PreparedUpstream(DesktopContract):
    host_id: str
    connection_changed: bool
    configuration: ProxyConfiguration


class ConnectorBinding(DesktopContract):
    host_id: str
    connector_id: str


class InvocationCompletion(DesktopContract):
    connector_id: str
    operation_name: str
    outcome: Literal["success", "failure"]


class AdministrationError(Exception):
    def __init__(self) -> None:
        super().__init__("Connector administration failed")


class AdministrationRejected(AdministrationError):
    pass
