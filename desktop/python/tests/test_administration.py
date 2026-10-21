import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from umbod_desktop.backend_integration.administration import BackendAdministration
from umbod_desktop.contracts import AdministrationError, AdministrationRejected
from umbod_desktop.ports import ConnectorAdministration


@pytest.mark.parametrize("status,error", [(403, AdministrationRejected), (409, AdministrationRejected), (500, AdministrationRejected)])
async def test_administration_translates_rejections_without_response_secrets(status: int, error: type[AdministrationError]) -> None:
    async def reject(request: Request) -> JSONResponse:
        assert request.headers["authorization"] == "Bearer private-token"
        return JSONResponse({"detail": "private-token"}, status_code=status)

    adapter = BackendAdministration(Starlette(routes=[Route("/api/admin/mcp-permissions/groups/desktop-owner", reject, methods=["POST"])]), "private-token")
    administration: ConnectorAdministration = adapter
    try:
        with pytest.raises(error) as caught:
            await administration.ensure_group("desktop-owner")
        assert "private-token" not in str(caught.value)
        assert caught.value.__suppress_context__
    finally:
        await adapter.close()
    assert adapter.client.is_closed


async def test_administration_translates_transport_errors_without_secrets() -> None:
    async def fail(request: Request) -> JSONResponse:
        raise httpx.ConnectError("private-token")

    adapter = BackendAdministration(Starlette(routes=[Route("/api/admin/mcp-permissions/groups/desktop-owner", fail, methods=["POST"])]), "private-token")
    administration: ConnectorAdministration = adapter
    try:
        with pytest.raises(AdministrationError) as caught:
            await administration.ensure_group("desktop-owner")
        assert not isinstance(caught.value, AdministrationRejected)
        assert "private-token" not in str(caught.value)
    finally:
        await adapter.close()
