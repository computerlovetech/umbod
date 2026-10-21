import httpx
import pytest

from umbod_desktop.backward_compatibility.adapters.administration import (
    BackendPrefixRepair,
)
from umbod_desktop.backward_compatibility.contracts import PrefixUpdate
from umbod_desktop.backward_compatibility.ports import PrefixRepair
from umbod_desktop.contracts import AdministrationError, AdministrationRejected


async def test_prefix_repair_updates_metadata_without_owning_client() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/api/admin/connectors/mcp/connector"
        assert request.content == b'{"tool_name_prefix":"Readable"}'
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
        repair: PrefixRepair = BackendPrefixRepair(client)
        await repair.update_prefix(PrefixUpdate(connector_id="connector", prefix="Readable"))
        assert not client.is_closed


@pytest.mark.parametrize("status", [403, 409, 500])
async def test_prefix_repair_maps_rejection_without_secrets(status: int) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "private-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
        repair: PrefixRepair = BackendPrefixRepair(client)
        with pytest.raises(AdministrationRejected) as caught:
            await repair.update_prefix(PrefixUpdate(connector_id="connector", prefix="Readable"))
        assert "private-token" not in str(caught.value)
        assert caught.value.__suppress_context__


async def test_prefix_repair_maps_transport_failure_without_secrets() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
        repair: PrefixRepair = BackendPrefixRepair(client)
        with pytest.raises(AdministrationError) as caught:
            await repair.update_prefix(PrefixUpdate(connector_id="connector", prefix="Readable"))
        assert not isinstance(caught.value, AdministrationRejected)
        assert "private-token" not in str(caught.value)
