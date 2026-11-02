from typing import Literal

import pytest
from pydantic import ValidationError

from umbod.core.administrator.connector_configuration import (
    ConfigurationError,
    ConfigurationRejected,
    ConfigurationResult,
    ConfigurationSucceeded,
    ConnectorConfigurableState,
    ConnectorDesiredState,
    ConnectorReference,
    ReadConnectorConfiguration,
    SystemDescriptionState,
    UpsertConnectorConfiguration,
)
from umbod.core.responses import OperationState
from umbod.mcp.administrator.tools import AdministratorConnectorConfigurationTools
from umbod.mcp.responses.progress import operation_progress_context
from umbod.mcp.tools.errors import BuiltinToolError


class ConfigurationService:
    def __init__(self, result: ConfigurationResult) -> None:
        self.result = result
        self.requests: list[ReadConnectorConfiguration | UpsertConnectorConfiguration] = []
        self.committed = False

    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        self.requests.append(request)
        return self.result

    async def upsert(self, request: UpsertConnectorConfiguration) -> ConfigurationResult:
        self.requests.append(request)
        self.committed = True
        return self.result


@pytest.fixture
def state() -> ConnectorConfigurableState:
    return ConnectorConfigurableState(
        connector=ConnectorReference(connector_kind="native", connector_id="private_connector"),
        capability_description=SystemDescriptionState(state="system", revision=0),
    )


async def invoke(
    tools: AdministratorConnectorConfigurationTools,
    operation: Literal["read", "upsert"],
    connector_id: str,
) -> ConnectorConfigurableState:
    if operation == "read":
        return await tools.read_connector_configuration("native", connector_id)
    return await tools.upsert_connector_configuration(
        "native", connector_id, ConnectorDesiredState(operations=()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "upsert"])
async def test_success_preserves_payload_and_marks_completed(
    operation: Literal["read", "upsert"], state: ConnectorConfigurableState,
) -> None:
    service = ConfigurationService(ConfigurationSucceeded(state=state))
    tools = AdministratorConnectorConfigurationTools(service, "groups")

    with operation_progress_context() as progress:
        result = await invoke(tools, operation, "private_connector")

    assert result == state
    assert len(service.requests) == 1
    assert progress.state == OperationState.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "upsert"])
async def test_rejection_remains_unknown_including_after_commit(
    operation: Literal["read", "upsert"],
) -> None:
    service = ConfigurationService(ConfigurationRejected(
        error=ConfigurationError(code="connector_not_found", message="private_connector"),
    ))
    tools = AdministratorConnectorConfigurationTools(service, "groups")

    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolError) as caught:
            await invoke(tools, operation, "private_connector")

    assert progress.state == OperationState.UNKNOWN
    assert service.committed == (operation == "upsert")
    assert caught.value.details.code == "connector_not_found"
    assert "private_connector" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "upsert"])
async def test_invalid_request_is_rejected_before_service_admission(
    operation: Literal["read", "upsert"], state: ConnectorConfigurableState,
) -> None:
    service = ConfigurationService(ConfigurationSucceeded(state=state))
    tools = AdministratorConnectorConfigurationTools(service, "groups")

    with operation_progress_context() as progress:
        with pytest.raises(ValidationError):
            await invoke(tools, operation, "")

    assert progress.state == OperationState.NOT_STARTED
    assert service.requests == []


@pytest.mark.asyncio
async def test_direct_call_without_progress_scope_preserves_payload(
    state: ConnectorConfigurableState,
) -> None:
    service = ConfigurationService(ConfigurationSucceeded(state=state))
    tools = AdministratorConnectorConfigurationTools(service, "groups")

    assert await invoke(tools, "read", "private_connector") == state
