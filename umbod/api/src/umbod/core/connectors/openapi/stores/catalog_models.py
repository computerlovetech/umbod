from pydantic import ConfigDict

from umbod.core.connectors.openapi.models import OpenApiEndpointCapability, OpenApiMetadata
from umbod.proxies import Model


class OpenApiCatalogHeader(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    metadata: OpenApiMetadata
    server_candidates: tuple[str, ...]
    approved_hosts: tuple[str, ...]
    selected_server_url: str
    operation_ids: tuple[str, ...]
    imported_at: str


class OpenApiOperationSummary(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    tags: tuple[str, ...]


class PersistedOpenApiOperation(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: OpenApiOperationSummary
    capability: OpenApiEndpointCapability
