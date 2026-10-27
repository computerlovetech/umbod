import pytest

from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential
from umbod.core.invocation import PermitAllConnectorInvocationPolicy

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ("available", "identity", "disconnect", "publication"))
async def test_duplicate_shared_and_personal_public_names_fail_closed(runtime_case: RuntimeCase, withdrawal: str) -> None:
    execution = await execution_case(runtime_case)
    if withdrawal == "identity":
        execution.contexts.contexts.clear()
    elif withdrawal == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif withdrawal == "publication":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    await install_shared_alias(runtime_case, True)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    for operation in (provider.list_tools(), provider.eligible_search_candidates(), provider.execute_tool("Personal_read", {"value": "same"}), provider.owns_tool("Personal_read"), provider.is_eligible("personal", "read")):
        with pytest.raises(Exception, match="public_tool_name_conflict"):
            await operation
    assert execution.transport.calls == []


async def install_shared_alias(runtime_case: RuntimeCase, published: bool) -> None:
    stores = runtime_case.bundle
    await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id="shared", display_name="Shared", tool_name_prefix="Personal", endpoint_url="https://shared.example/mcp")))
    await stores.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id="shared")))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id="shared", discovered_at=runtime_case.query.now, tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id="shared", downstream_name="read"), title="Shared", description="Shared", input_schema={"type": "object"}),))))
    if published:
        await stores.publishing.publish_connector("shared")
    await stores.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="shared", capability_kind="tool", capability_key="read"), ActivationStatus.ENABLED)


@pytest.mark.asyncio
async def test_unpublished_shared_draft_does_not_claim_personal_runtime_name(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    await install_shared_alias(runtime_case, False)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    assert [tool.name for tool in await provider.list_tools()] == ["Personal_read"]
    assert await provider.owns_tool("Personal_read")
    assert not (await provider.execute_tool("Personal_read", {"value": "same"})).is_error
    assert len(execution.transport.calls) == 1
