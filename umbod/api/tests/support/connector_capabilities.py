from dataclasses import dataclass
from typing import Any, Literal

from fastapi.testclient import TestClient


CapabilityKind = Literal["prompts", "resources"]


@dataclass(frozen=True)
class CapabilityCatalogResponse:
    status_code: int
    body: dict[str, Any]


class ConnectorCapabilityAdminDriver:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def programmed_catalog(
        self, connector_id: str, capability_kind: CapabilityKind
    ) -> CapabilityCatalogResponse:
        response = self._client.get(f"/admin/connectors/catalog/{connector_id}/{capability_kind}")
        return CapabilityCatalogResponse(response.status_code, response.json())

    def proxied_catalog(
        self, connector_id: str, capability_kind: CapabilityKind
    ) -> CapabilityCatalogResponse:
        response = self._client.get(f"/admin/connectors/mcp/{connector_id}/{capability_kind}")
        return CapabilityCatalogResponse(response.status_code, response.json())
