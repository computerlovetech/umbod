import httpx

from ...contracts import AdministrationError, AdministrationRejected
from ..contracts import PrefixUpdate


class BackendPrefixRepair:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def update_prefix(self, update: PrefixUpdate) -> None:
        try:
            response = await self.client.patch(
                f"/api/admin/connectors/mcp/{update.connector_id}",
                json={"tool_name_prefix": update.prefix},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise AdministrationRejected() from None
        except httpx.HTTPError:
            raise AdministrationError() from None
