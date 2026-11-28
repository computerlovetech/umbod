import json
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.routing import APIRoute

from umbod.core.connectors.portable.managed.catalog_models import (
    ManagedConfigurationFieldRejected,
    ManagedConfigurationRejected,
)
from umbod.core.connectors.portable.managed.configuration_schema import (
    MAX_CONFIGURATION_FIELDS,
    MAX_CONFIGURATION_VALUE_LENGTH,
)
from umbod.core.connectors.portable.managed.ports import (
    ManagedCatalogUnavailable,
    ManagedConfigurationWriteUnconfirmed,
    ManagedConnectorNotFound,
)

from .dependencies import PortableCatalogAccess
from .models import (
    ConfigurationInput,
    ConnectorConfigurationResponse,
    ConnectorList,
    configuration_response,
)

_MAX_REQUEST_BYTES = (
    MAX_CONFIGURATION_FIELDS * (12 * MAX_CONFIGURATION_VALUE_LENGTH + 320) + 1024
)


class PortableCatalogRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except ManagedConnectorNotFound:
                raise HTTPException(
                    404, detail={"code": "portable_connector_not_found"}
                ) from None
            except ManagedCatalogUnavailable:
                raise HTTPException(
                    503, detail={"code": "portable_connector_catalog_unavailable"}
                ) from None
            except ManagedConfigurationWriteUnconfirmed:
                raise HTTPException(
                    503,
                    detail={
                        "code": "configuration_write_unconfirmed",
                        "message": "Reload the configuration before retrying.",
                    },
                ) from None
            except ManagedConfigurationFieldRejected as error:
                raise HTTPException(
                    422, detail={"code": error.code, "field": error.field_name}
                ) from None
            except ManagedConfigurationRejected as error:
                raise HTTPException(422, detail={"code": error.code}) from None

        return handle


router = APIRouter(
    prefix="/portable-connectors",
    tags=["portable connectors"],
    route_class=PortableCatalogRoute,
)


@router.get("")
async def list_portable_connectors(catalog: PortableCatalogAccess) -> ConnectorList:
    return ConnectorList(connectors=await catalog.list_connectors())


@router.get("/{connector_id}/configuration")
async def read_portable_configuration(
    connector_id: str, catalog: PortableCatalogAccess
) -> ConnectorConfigurationResponse:
    managed = await catalog.read_configuration(_managed_id(connector_id))
    return configuration_response(managed)


@router.put(
    "/{connector_id}/configuration",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ConfigurationInput.model_json_schema()}
            },
        },
    },
)
async def replace_portable_configuration(
    connector_id: str,
    catalog: PortableCatalogAccess,
    request: Request,
) -> ConnectorConfigurationResponse:
    managed = await catalog.read_configuration(_managed_id(connector_id))
    body = await _configuration_input(request)
    updated = await catalog.replace_configuration(managed, body.configuration)
    return configuration_response(updated)


def _managed_id(connector_id: str) -> UUID:
    try:
        return UUID(connector_id)
    except ValueError:
        raise ManagedConnectorNotFound() from None


async def _configuration_input(request: Request) -> ConfigurationInput:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_REQUEST_BYTES:
            raise ManagedConfigurationRejected("configuration_too_large")
        body.extend(chunk)
    try:
        payload: object = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_fields,
            parse_constant=_reject_constant,
        )
        return ConfigurationInput.model_validate(payload)
    except ValueError, RecursionError:
        raise ManagedConfigurationRejected("invalid_configuration") from None


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Duplicate configuration request key")
    return fields


def _reject_constant(_value: str) -> object:
    raise ValueError("Invalid configuration request constant")
