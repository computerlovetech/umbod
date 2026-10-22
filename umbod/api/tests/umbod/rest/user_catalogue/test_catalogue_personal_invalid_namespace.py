import pytest
from fastmcp.exceptions import ToolError

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case as runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition
from umbod.core.connectors.downstream_mcp.user_catalogue import PersonalNamespace
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.user_catalogue import CatalogueCapability, CatalogueConnector, CatalogueSource
from umbod.core.user_catalogue.in_memory import InMemoryCatalogueSource
from umbod.rest.user_catalogue.projection import CollisionSafeSource, gateway_tools_unavailable


@pytest.mark.asyncio
async def test_real_empty_normalized_personal_stem_keeps_selection_but_never_advertises_tools(
    runtime_case: RuntimeCase,
) -> None:
    execution = await execution_case(runtime_case)
    stored = await runtime_case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))
    definition = OAuthConnectorDefinition.model_validate(dict(stored.definition.model_dump(), tool_name_prefix="___"))
    await runtime_case.bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    with pytest.raises(ToolError, match="public_tool_name_conflict"):
        await provider.is_personal_tool_name("read")
    connector = CatalogueConnector(
        connector_id="personal", kind="downstream_mcp", display_name="Personal",
        capability_description="Personal capabilities", ownership="personal",
        capabilities=(CatalogueCapability(kind="tool", key="read", name="Read", description="Read"),),
    )
    names = {("downstream_mcp", "personal", "tool", "read"): "read"}
    namespace = PersonalNamespace((definition,))
    source: CatalogueSource = CollisionSafeSource(
        InMemoryCatalogueSource((connector,)), names, namespace, frozenset(),
    )
    connectors = await source.list_connectors()
    assert connectors == (connector.model_copy(update={"capabilities": ()}),)
    assert gateway_tools_unavailable(names, namespace, frozenset(("personal",)))
