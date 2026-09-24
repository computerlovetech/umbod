from typing import Any

from pydantic import ConfigDict, model_validator

from umbod.proxies import Model

from umbod.core.capabilities.descriptions.domain import CapabilityDescription
from umbod.core.capabilities.tools.names import normalize_tool_name_prefix
from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate


class CreateOpenApiConnector(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str
    tool_name_prefix: str
    capability_description: CapabilityDescription

    @model_validator(mode="before")
    @classmethod
    def default_missing_tool_name_prefix(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "tool_name_prefix" in data:
            return data
        return {
            **data,
            "tool_name_prefix": normalize_tool_name_prefix(str(data.get("display_name", ""))),
        }


class OpenApiConnector(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    display_name: str
    tool_name_prefix: str
    capability_description: CapabilityDescription
    created_at: str
    updated_at: str

class ImportOpenApiCatalog(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    source_document: dict[str, object]
    candidate: ImportedOpenApiCandidate
    approved_hosts: tuple[str, ...]
    selected_server_url: str | None = None


class OpenApiConnectorCatalog(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    source_document: dict[str, object]
    candidate: ImportedOpenApiCandidate
    approved_hosts: tuple[str, ...]
    selected_server_url: str
    operation_ids: tuple[str, ...]
    imported_at: str


class ReplaceCurrentOpenApiCatalog(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector: OpenApiConnector
    catalog: OpenApiConnectorCatalog
