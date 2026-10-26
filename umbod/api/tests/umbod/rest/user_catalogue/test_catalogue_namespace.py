import pytest

from umbod.core.capabilities import AbsentCapabilityOutputSchema

from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.user_catalogue import PersonalNamespace
from umbod.core.user_catalogue import CatalogueCapability, CatalogueConnector, CatalogueSource, CatalogueToolCapability, UserCatalogueReader, UserCatalogueService
from umbod.core.user_catalogue.in_memory import InMemoryCatalogueSource
from umbod.rest.user_catalogue.projection import CollisionSafeSource, duplicate_names, gateway_tools_unavailable


@pytest.mark.asyncio
async def test_personal_namespace_reservations_hide_shared_tools_even_when_personal_support_is_disabled() -> None:
    definition = OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", tool_name_prefix="reserved-prefix",
        capability_description="Personal capabilities", endpoint_url="https://private.example/mcp",
        public_path="/mcp/proxies/personal", authorization_mode="personal",
    )
    connector = CatalogueConnector(
        connector_id="shared", kind="native", display_name="Shared",
        capability_description="Shared capabilities", ownership="shared",
        capabilities=(CatalogueToolCapability(kind="tool", key="lookup", name="Lookup", description="Lookup", input_schema={}, output_schema=AbsentCapabilityOutputSchema()),),
    )
    names = {("native", "shared", "tool", "lookup"): "reserved_prefix_lookup"}
    source: CatalogueSource = CollisionSafeSource(
        InMemoryCatalogueSource((connector,)), names, PersonalNamespace((definition,)), frozenset(),
    )
    reader: UserCatalogueReader = UserCatalogueService((source,), False, "identity")
    assert (await reader.read()).connectors == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["personal_observations", "provider_names", "reserved_native"])
async def test_gateway_global_invalidity_suppresses_every_tool_but_preserves_personal_selection(
    conflict: str,
) -> None:
    definition = OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", tool_name_prefix="Personal",
        capability_description="Personal capabilities", endpoint_url="https://private.example/mcp",
        public_path="/mcp/proxies/personal", authorization_mode="personal",
    )
    tool = CatalogueToolCapability(kind="tool", key="read", name="Read", description="Read", input_schema={}, output_schema=AbsentCapabilityOutputSchema())
    connectors = (
        CatalogueConnector(connector_id="healthy", kind="native", display_name="Healthy",
                           capability_description="Healthy capabilities", ownership="shared", capabilities=(tool,)),
        CatalogueConnector(connector_id="personal", kind="downstream_mcp", display_name="Personal",
                           capability_description="Personal capabilities", ownership="personal", capabilities=(tool,)),
    )
    names = {
        ("native", "healthy", "tool", "read"): "Healthy_read",
        ("downstream_mcp", "personal", "tool", "read"): "Personal_read",
    }
    if conflict == "personal_observations":
        names[("downstream_mcp", "personal", "tool", "other")] = "Personal_read"
    elif conflict == "provider_names":
        names[("downstream_mcp", "first", "tool", "lookup")] = "Shared_lookup"
        names[("downstream_mcp", "second", "tool", "lookup")] = "Shared_lookup"
    else:
        names[("native", "unpublished", "tool", "reserved")] = "Personal_reserved"
    namespace = PersonalNamespace((definition,))
    assert gateway_tools_unavailable(names, namespace, frozenset(("personal",)))
    source: CatalogueSource = CollisionSafeSource(
        InMemoryCatalogueSource(connectors), names, namespace,
        frozenset(identity for identity in names if identity[2] == "tool"),
    )
    assert await source.list_connectors() == (connectors[1].model_copy(update={"capabilities": ()}),)


@pytest.mark.asyncio
async def test_resource_and_resource_template_uri_collisions_are_not_advertised() -> None:
    connector = CatalogueConnector(
        connector_id="shared", kind="downstream_mcp", display_name="Shared",
        capability_description="Shared capabilities", ownership="shared",
        capabilities=(CatalogueCapability(kind="resource", key="data://item", name="Item", description="Item"),),
    )
    names = {
        ("downstream_mcp", "shared", "resource", "data://item"): "data://item",
        ("downstream_mcp", "another", "resource_template", "data://item"): "data://item",
    }
    source: CatalogueSource = CollisionSafeSource(
        InMemoryCatalogueSource((connector,)), names, PersonalNamespace(()), duplicate_names(names),
    )
    assert await source.list_connectors() == ()
