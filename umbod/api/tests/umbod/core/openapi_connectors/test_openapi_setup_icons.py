import asyncio
import json

import pytest
from pydantic import SecretStr

from tests.persistence_runtime import create_inmemory_runtime
from tests.umbod.core.openapi_connectors.test_openapi_management_acceptance import SequenceClock, SequenceIds
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.importing import DefaultOpenApiImportPreparer, InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import AllowActivationPermissionChangeGuard, compose_openapi_connector_management
from umbod.core.connectors.openapi.management.configuration import OpenApiBearerConfiguration, OpenApiConfigurationStatus
from umbod.core.connectors.openapi.management.models import CreateOpenApiConnector, OpenApiConnector
from umbod.core.connectors.openapi.management.setup import OpenApiConnectorSetupService
from umbod.core.connectors.openapi.management.setup_ports import OpenApiConnectorSetupPort, OpenApiSetupInvalidRequest, OpenApiSetupManagementPort, SetupOpenApiConnector
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.icons import Favicon, FaviconDiscovery, FaviconDiscoveryRequest, FaviconDiscoveryResult, FaviconDiscoveryTimedOut, FaviconFound, FaviconNotFound


class RecordingDiscovery:
    def __init__(self, result: FaviconDiscoveryResult) -> None:
        self.result = result
        self.requests: list[FaviconDiscoveryRequest] = []

    async def discover(self, request: FaviconDiscoveryRequest) -> FaviconDiscoveryResult:
        self.requests.append(request)
        return self.result


class CancelledDiscovery:
    async def discover(self, request: FaviconDiscoveryRequest) -> FaviconDiscoveryResult:
        raise asyncio.CancelledError


class UnauthenticatedConfiguration:
    async def status(self, connector_id: str) -> OpenApiConfigurationStatus:
        return OpenApiConfigurationStatus(configured=False, authentication_type="none")

    async def configure(self, connector_id: str, bearer_token: SecretStr) -> OpenApiConfigurationStatus:
        raise AssertionError("Unexpected bearer configuration")

    async def clear(self, connector_id: str) -> OpenApiConfigurationStatus:
        return await self.status(connector_id)

    async def resolve(self, connector_id: str) -> OpenApiBearerConfiguration | None:
        return None


@pytest.fixture
def management() -> OpenApiSetupManagementPort:
    return compose_openapi_connector_management(
        store=OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE),
        ids=SequenceIds(), clock=SequenceClock(), permission_change_guard=AllowActivationPermissionChangeGuard(),
    )


@pytest.fixture
def request_model() -> SetupOpenApiConnector:
    return SetupOpenApiConnector(
        display_name="Example", tool_name_prefix="example", capability_description="Manage example resources",
        document={
            "openapi": "3.1.0", "info": {"title": "Example", "version": "1"},
            "servers": [{"url": "https://unapproved.example.test"}, {"url": "https://api.example.test/v2"}],
            "x-logo": {"url": "https://attacker.example.test/icon.svg"},
            "paths": {"/items": {"get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}}}},
        },
        approved_hosts=("api.example.test",), authentication_type="none", bearer_token=SecretStr(""),
    )


def setup_port(management: OpenApiSetupManagementPort, discovery: FaviconDiscovery) -> OpenApiConnectorSetupPort:
    return OpenApiConnectorSetupService(management, InMemoryOpenApiCandidateImporter(), DefaultOpenApiImportPreparer(), UnauthenticatedConfiguration(), discovery)


@pytest.mark.asyncio
@pytest.mark.parametrize("result, expected_icon_url", [
    (FaviconFound(icon=Favicon(url="https://api.example.test/icon.svg", mime_type="image/svg+xml"), strategy="test"), "https://api.example.test/icon.svg"),
    (FaviconNotFound(), ""),
    (FaviconDiscoveryTimedOut(), ""),
])
async def test_setup_discovers_only_selected_server_and_saves_icon(
    management: OpenApiSetupManagementPort, request_model: SetupOpenApiConnector,
    result: FaviconDiscoveryResult, expected_icon_url: str,
) -> None:
    discovery = RecordingDiscovery(result)
    connector = await setup_port(management, discovery).setup(request_model)
    assert discovery.requests == [FaviconDiscoveryRequest(endpoint_url="https://api.example.test/v2", advertised_icons=())]
    assert connector.icon_url == expected_icon_url
    assert (await management.get_connector(connector.connector_id)).icon_url == expected_icon_url


@pytest.mark.asyncio
@pytest.mark.parametrize("updates", [{"display_name": " "}, {"document": {}}, {"approved_hosts": ("other.example.test",)}, {"authentication_type": "bearer", "bearer_token": SecretStr(" ")}])
async def test_invalid_setup_does_not_discover(
    management: OpenApiSetupManagementPort, request_model: SetupOpenApiConnector, updates: dict[str, object],
) -> None:
    discovery = RecordingDiscovery(FaviconNotFound())
    with pytest.raises(OpenApiSetupInvalidRequest):
        await setup_port(management, discovery).setup(request_model.model_copy(update=updates))
    assert discovery.requests == []


@pytest.mark.asyncio
async def test_discovery_caller_cancellation_propagates(
    management: OpenApiSetupManagementPort, request_model: SetupOpenApiConnector,
) -> None:
    with pytest.raises(asyncio.CancelledError):
        await setup_port(management, CancelledDiscovery()).setup(request_model)


@pytest.mark.parametrize("model_type", [CreateOpenApiConnector, OpenApiConnector])
def test_legacy_serialized_connector_without_icon_remains_valid(model_type: type[CreateOpenApiConnector] | type[OpenApiConnector]) -> None:
    fields = {"display_name": "Example", "tool_name_prefix": "example", "capability_description": "Manage example resources"}
    if model_type is OpenApiConnector:
        fields.update(connector_id="legacy", created_at="2026-01-01", updated_at="2026-01-01")
    assert model_type.model_validate_json(json.dumps(fields)).icon_url == ""


@pytest.mark.asyncio
async def test_direct_creation_preserves_requested_icon(management: OpenApiSetupManagementPort) -> None:
    connector = await management.create_connector(CreateOpenApiConnector(display_name="Example", tool_name_prefix="example", capability_description="Manage example resources", icon_url="https://api.example.test/icon.png"))
    assert (await management.get_connector(connector.connector_id)).icon_url == "https://api.example.test/icon.png"
