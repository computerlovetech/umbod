from typing import Any

import httpx
from pydantic import BaseModel
from starlette.types import ASGIApp

from ..contracts import (
    AdministrationError,
    AdministrationRejected,
    ConnectorCreation,
    ConnectorDefinition,
    ToolGrant,
    ToolSelection,
)


class ConnectorReference(BaseModel):
    connector_id: str


class ConnectorInventory(BaseModel):
    connectors: tuple[ConnectorReference, ...]


class ToolReference(BaseModel):
    name: str


class ToolInventory(BaseModel):
    tools: tuple[ToolReference, ...]


def connector_definition(payload: dict[str, Any]) -> ConnectorDefinition:
    return ConnectorDefinition.model_validate({
        field: payload[field] for field in ConnectorDefinition.model_fields
    })


class BackendAdministration:
    def __init__(self, api: ASGIApp, token: str) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://127.0.0.1",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _request(
        self, method: str, path: str, body: Any = None
    ) -> dict[str, Any]:
        try:
            response = await self.client.request(method, "/api/admin" + path, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise AdministrationRejected() from None
        except httpx.HTTPError:
            raise AdministrationError() from None
        return response.json() if response.content else {}

    async def inventory(self) -> tuple[ConnectorDefinition, ...]:
        listed = ConnectorInventory.model_validate(await self._request("GET", "/connectors/mcp"))
        return tuple([
            connector_definition(await self._request("GET", f"/connectors/mcp/{item.connector_id}"))
            for item in listed.connectors
        ])

    async def create(self, command: ConnectorCreation) -> ConnectorDefinition:
        payload = command.model_dump(exclude={"configuration"})
        created = await self._request("POST", "/connectors/mcp", {
            "metadata": payload,
            "configuration": command.configuration.model_dump(),
        })
        return connector_definition(created)

    async def discover(self, connector_id: str) -> None:
        await self._request("POST", f"/connectors/mcp/{connector_id}/discoveries")

    async def tool_names(self, connector_id: str) -> tuple[str, ...]:
        tools = ToolInventory.model_validate(await self._request("GET", f"/connectors/mcp/{connector_id}/tools"))
        return tuple(tool.name for tool in tools.tools)

    async def enable_tools(self, selection: ToolSelection) -> None:
        await self._request("PUT", f"/connectors/mcp/{selection.connector_id}/tools/activation", {
            "tools": [{"tool_id": name, "activation_status": "enabled"} for name in selection.names]
        })

    async def ensure_group(self, group_id: str) -> None:
        await self._request("POST", f"/mcp-permissions/groups/{group_id}")

    async def grant_tools(self, grant: ToolGrant) -> None:
        await self._request("PUT", f"/mcp-permissions/groups/{grant.group_id}/permissions", {
            "capabilities": [{
                "connector_id": grant.selection.connector_id,
                "capability_kind": "tool",
                "capability_key": name,
                "permission_status": "enabled",
            } for name in grant.selection.names]
        })

    async def publish(self, connector_id: str) -> None:
        await self._request("PUT", f"/connectors/mcp/{connector_id}/publication")

    async def close(self) -> None:
        await self.client.aclose()
