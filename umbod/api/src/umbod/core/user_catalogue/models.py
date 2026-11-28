from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field

from umbod.proxies import Model
from umbod.core.capabilities.domain import CapabilityOutputSchema, JsonObject
from umbod.core.invocation import ConnectorKind


class CatalogueModel(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogueCapability(CatalogueModel):
    kind: Literal["prompt", "resource", "resource_template"]
    key: str
    name: str
    description: str


class CatalogueToolCapability(CatalogueModel):
    kind: Literal["tool"]
    key: str
    name: str
    description: str
    input_schema: JsonObject
    output_schema: CapabilityOutputSchema


class CatalogueConnector(CatalogueModel):
    connector_id: str
    kind: ConnectorKind
    display_name: str
    icon_url: str = Field(default="", exclude_if=lambda value: value == "")
    capability_description: str
    ownership: Literal["shared", "personal"]
    capabilities: tuple[
        Annotated[Union[CatalogueCapability, CatalogueToolCapability], Field(discriminator="kind")], ...
    ]


class UserCatalogue(CatalogueModel):
    identity_key: str
    personal_enabled: bool
    connectors: tuple[CatalogueConnector, ...]
