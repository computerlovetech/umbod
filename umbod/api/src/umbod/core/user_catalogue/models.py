from typing import Literal

from pydantic import BaseModel, ConfigDict

from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.invocation import ConnectorKind


class CatalogueModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogueCapability(CatalogueModel):
    kind: CapabilityKind
    key: str
    name: str
    description: str


class CatalogueConnector(CatalogueModel):
    connector_id: str
    kind: ConnectorKind
    display_name: str
    capability_description: str
    ownership: Literal["shared", "personal"]
    capabilities: tuple[CatalogueCapability, ...]


class UserCatalogue(CatalogueModel):
    identity_key: str
    personal_enabled: bool
    connectors: tuple[CatalogueConnector, ...]
