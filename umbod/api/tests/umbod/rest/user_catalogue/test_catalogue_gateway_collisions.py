from tests.support.native_tool_states import enabled_native_tool_states
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals.execution import SignalToolExecutionPipelineFactory
from umbod.mcp.metrics import PrometheusMcpMetricsRecorder
from umbod.mcp.logging import create_default_mcp_audit_recorder

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from tests.persistence_runtime import create_inmemory_runtime, prepared_sqlite_runtime
from tests.support.connector_plugins import TestConnectorAdminConfiguration as NativeConfiguration, TestConnectorPlugin
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case as runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.config import AppConfig
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores, ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, create_downstream_mcp_stores
from umbod.core.connectors.native.registry import ConnectorRegistration
from umbod.core.connectors.native.runtime.tools import ConcreteConnectorToolMapping
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.mcp.connectors.native.tools import RuntimeConnectorToolRegistry, register_connector_tools
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.mcp.logging import create_default_mcp_tool_invocation_log_sink
from umbod.rest.main import create_app


def _registrations() -> tuple[ConnectorRegistration, ...]:
    return tuple(
        dict(TestConnectorPlugin.registration(), id=connector_id, tool_name_prefix=prefix)
        for connector_id, prefix in (("alpha", "collision"), ("healthy", "healthy"))
    )


async def _shared_collision(stores: DownstreamMcpStores, now: datetime) -> None:
    await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
        connector_id="beta", display_name="Shared", tool_name_prefix="collision", endpoint_url="https://shared.example/mcp",
    )))
    await stores.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id="beta")))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="beta", discovered_at=now, tools=(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id="beta", downstream_name="echo"), title="Echo",
            description="Echo", input_schema={"type": "object"},
        ),),
    )))
    await stores.publishing.publish_connector("beta")
    await stores.activations.set_status(CapabilityRef("downstream_mcp", "beta", "tool", "echo"), ActivationStatus.ENABLED)


def _prepare_http(client: TestClient, publish_alpha: bool) -> None:
    for connector_id in ("alpha", "healthy"):
        url = f"/api/admin/connectors/catalog/{connector_id}"
        client.put(url + "/configuration", json={"configuration": {
            "instance_name": connector_id, "api_key": "test-key", "default_response": "hello",
        }}).raise_for_status()
        if connector_id != "alpha" or publish_alpha:
            client.put(url + "/publication").raise_for_status()
        client.put(url + "/tools/activation", json={"tools": [{
            "tool_id": "echo", "activation_status": "enabled",
        }]}).raise_for_status()
    client.put("/api/admin/connectors/catalog/healthy/prompts/activation", json={"prompts": [{
        "prompt_id": "test_prompt", "activation_status": "enabled",
    }]}).raise_for_status()
    client.put("/api/admin/mcp-permissions/groups/umbod-admins/permissions", json={"capabilities": [
        {"connector_id": connector_id, "capability_kind": "tool", "capability_key": "echo", "permission_status": "enabled"}
        for connector_id in ("beta", "healthy")
    ] + [{"connector_id": "healthy", "capability_kind": "prompt", "capability_key": "test_prompt", "permission_status": "enabled"}]}).raise_for_status()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode"])
@pytest.mark.parametrize("publish_alpha", [True, False])
async def test_catalogue_gateway_collision_suppresses_unrelated_tools_but_preserves_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, publish_alpha: bool,
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text(json.dumps({"connectors": [{"id": identifier} for identifier in ("alpha", "healthy")]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        rest={"metrics_enabled": False}, mcp={"connector_tool_exposure_mode": mode},
        connector_security={"configuration_secret": "catalogue-collision-secret"},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "catalogue.sqlite")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )
    runtime = await prepared_sqlite_runtime(tmp_path / "catalogue.sqlite")
    stores = await create_downstream_mcp_stores("catalogue-collision-secret", runtime.database)
    await _shared_collision(stores, datetime.now(timezone.utc))
    await runtime.shutdown()
    with TestClient(create_app(settings, _registrations())) as client:
        _prepare_http(client, publish_alpha)
        response = client.get("/api/me/catalogue")
        response.raise_for_status()
        capabilities = [capability for connector in response.json()["connectors"] for capability in connector["capabilities"]]
        assert any(capability["kind"] == "prompt" for capability in capabilities)
        tools = [capability for capability in capabilities if capability["kind"] == "tool"]
        if mode == "flat":
            healthy = next(connector for connector in response.json()["connectors"] if connector["connector_id"] == "healthy")
            assert any(capability["kind"] == "tool" for capability in healthy["capabilities"])
        else:
            assert tools == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode"])
@pytest.mark.parametrize("publish_alpha", [True, False])
async def test_actual_runtime_rejects_gateway_collisions_without_disabling_unrelated_flat_tool(
    runtime_case: RuntimeCase, mode: str, publish_alpha: bool,
) -> None:
    execution = await execution_case(runtime_case)
    await _shared_collision(runtime_case.bundle, runtime_case.query.now)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    runtime = create_inmemory_runtime()
    configurations = InMemoryConnectorCurrentConfigurationStore()
    publishing = ConnectorPublishingStoreService(runtime.database, PUBLICATION_STATE_TABLE)
    mappings: list[ConcreteConnectorToolMapping] = []

    def operation() -> dict[str, str]:
        return {"result": "healthy"}

    for connector_id, prefix in (("alpha", "collision"), ("healthy", "healthy")):
        await configurations.save_current_configuration(connector_id, NativeConfiguration(
            instance_name=connector_id, api_key="test-key", default_response="hello",
        ))
        if connector_id != "alpha" or publish_alpha:
            await publishing.publish_connector(connector_id)
        mappings.append(ConcreteConnectorToolMapping(
            connector_id=connector_id, operation_name="echo", description="Echo", operation=operation,
            parameters={}, tool_name_prefix=prefix,
        ))
    public = FastMCP("catalogue-collision-parity")
    signals = create_mcp_signals(create_default_mcp_tool_invocation_log_sink(), PrometheusMcpMetricsRecorder(), create_default_mcp_audit_recorder("test"))
    await register_connector_tools(
        public,
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()),
        connector_registrations=_registrations(),
        connector_configuration_store=configurations,
        connector_publishing_store=publishing,
        connector_tool_mappings=mappings,
        connector_tool_runtime_state_store=enabled_native_tool_states(
            *((mapping.connector_id, mapping.operation_name) for mapping in mappings)
        ),
        connector_tool_exposure_mode=mode,
    )
    if mode == "flat":
        public.add_provider(provider)
        async with Client(public) as client:
            assert "healthy_echo" in {tool.name for tool in await client.list_tools()}
            assert not (await client.call_tool("healthy_echo", {})).is_error
    else:
        registry = cast(RuntimeConnectorToolRegistry, public.connector_tool_registry)
        registry.add_gateway_provider(provider)
        with pytest.raises(ToolError, match="Tool is not available"):
            await registry.eligible_search_candidates(UnrestrictedConnectorTools())
        with pytest.raises(ToolError, match="Tool is not available"):
            await registry.execute_tool("healthy_echo", {}, UnrestrictedConnectorTools())
    await runtime.shutdown()
