import pytest

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema, CapabilityAvailability, CapabilityIdentity,
    InMemoryCapabilityCatalog, NormalizedCapability,
)
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.invocation import ConnectorKind
from umbod.core.permissions.domain import ConnectorCapabilityRef, GroupPermissionSet, GroupPermissionSummary
from umbod.core.user_catalogue import CatalogueConnector, CatalogueSource, UserCatalogueReader, UserCatalogueService
from umbod.core.user_catalogue.in_memory import InMemoryCatalogueSource
from umbod.core.user_catalogue.shared import ExplicitCapabilityPermissions, SharedCatalogueSource


class CurrentGrants:
    def __init__(self, capabilities: tuple[ConnectorCapabilityRef, ...]) -> None:
        self.capabilities = capabilities

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        return GroupPermissionSet(group_id, ("weather",), self.capabilities)

    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        return (GroupPermissionSummary(group_id="team"),)

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        return (await self.list_group_permissions("team"),)


class AvailabilityGates:
    def __init__(self, published: bool, active: bool, ready: bool) -> None:
        self.published = published
        self.active = active
        self.ready = ready

    async def is_published(self, identity: CapabilityIdentity) -> bool:
        return self.published

    async def is_enabled(self, identity: CapabilityIdentity) -> bool:
        return self.active

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        return self.ready


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "openapi", "downstream_mcp"])
@pytest.mark.parametrize("capability_kind", ["tool", "prompt", "resource", "resource_template"])
@pytest.mark.parametrize("published,active,ready", [
    (True, True, True), (False, True, True), (True, False, True), (True, True, False),
])
async def test_catalogue_contract_requires_every_current_shared_gate_and_explicit_capability_grants(
    kind: ConnectorKind, capability_kind: CapabilityKind, published: bool, active: bool, ready: bool,
) -> None:
    identity = CapabilityIdentity(
        connector_kind=kind, connector_id="weather", capability_kind=capability_kind,
        capability_key="lookup",
    )
    capability = NormalizedCapability(
        identity=identity, title="Readable title", description="Safe description",
        input_schema={"secret_administrative_schema": True}, output_schema=AbsentCapabilityOutputSchema(),
        connector_display_name="Weather", connector_capability_description="Weather capabilities",
    )
    grants = CurrentGrants(())
    gates = AvailabilityGates(published, active, ready)
    source: CatalogueSource = SharedCatalogueSource(
        InMemoryCapabilityCatalog((capability,)),
        CapabilityAvailability(gates, gates, gates, ExplicitCapabilityPermissions(grants, ("team",))),
        SystemConnectorCapabilityDescriptionOverrideStore(),
    )
    assert await source.list_connectors() == ()
    grants.capabilities = (ConnectorCapabilityRef("weather", capability_kind, "lookup"),)
    connectors = await source.list_connectors()
    if published and active and ready:
        assert connectors[0].capabilities[0].name == "Readable title"
        assert "secret_administrative_schema" not in connectors[0].model_dump_json()
    else:
        assert connectors == ()
    grants.capabilities = ()
    assert await source.list_connectors() == ()


@pytest.mark.asyncio
async def test_in_memory_source_composes_through_public_reader_contract() -> None:
    connector = CatalogueConnector(
        connector_id="personal", kind="downstream_mcp", display_name="Personal",
        capability_description="Permitted personal tools", ownership="personal", capabilities=(),
    )
    source: CatalogueSource = InMemoryCatalogueSource((connector,))
    reader: UserCatalogueReader = UserCatalogueService((source,), True, "opaque-identity")
    catalogue = await reader.read()
    assert catalogue.identity_key == "opaque-identity"
    assert catalogue.connectors == (connector,)
