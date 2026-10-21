from dataclasses import dataclass
from typing import Optional

import pytest
import pytest_asyncio
from pydantic import SecretStr

from tests.persistence_runtime import create_inmemory_runtime
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    SetCapabilityDescriptionOverride,
)
from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_connections import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionService,
    PersonalConnectorInventory,
    PersonalConnectorInventoryService,
    PersonalConnectorQuery,
    PersonalConnectorUnavailable,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
    SetPersonalConnectorEnablement,
    VerifiedGroupMembership,
)
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores, SaveConnectorDefinition, create_downstream_mcp_stores
from umbod.core.permissions import GroupPermissionStore
from umbod.core.permissions.domain import ConnectorCapabilityRef, SaveGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_permission_store


class OwnerPrincipalProvider:
    def __init__(self, subject: str, namespace: str) -> None:
        self._principal = CanonicalPrincipal(namespace=namespace, subject=subject)

    async def get_principal(self) -> Optional[CanonicalPrincipal]:
        return self._principal


@dataclass(frozen=True)
class InventoryFixture:
    stores: DownstreamMcpStores
    permissions: GroupPermissionStore
    descriptions: ConnectorCapabilityDescriptionOverrideStore

    def inventory(self, subject: str = "alice", namespace: str = "trusted") -> PersonalConnectorInventory:
        return PersonalConnectorInventoryService(
            self.stores.definitions, self.stores.publishing, self.permissions,
            VerifiedGroupMembership(group_ids=("team",)),
            PersonalConnectionService(OwnerPrincipalProvider(subject, namespace), self.stores.personal_connections),
            self.descriptions,
        )


@pytest_asyncio.fixture
async def inventory_fixture() -> InventoryFixture:
    database = create_inmemory_runtime().database
    stores = await create_downstream_mcp_stores("test-secret", database)
    for connector_id, mode in (("zeta", "personal"), ("alpha", "personal"), ("shared", "shared"), ("capability-only", "personal")):
        await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
            connector_id=connector_id, display_name=connector_id,
            endpoint_url="https://tools.example/mcp", authorization_mode=mode,
        )))
        await stores.publishing.publish_connector(connector_id)
    permissions = await create_group_permission_store(database)
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(
        group_id="team", connector_ids=("zeta", "alpha", "shared"),
        capabilities=(ConnectorCapabilityRef(connector_id="capability-only", capability_kind="tool", capability_key="lookup"),),
    ))
    descriptions = await ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(database).create()
    return InventoryFixture(stores, permissions, descriptions)


@pytest.mark.asyncio
async def test_inventory_is_sorted_personal_only_and_requires_connector_grant(inventory_fixture: InventoryFixture) -> None:
    result = await inventory_fixture.inventory().list()
    assert [item.connector_id for item in result.connectors] == ["alpha", "zeta"]
    with pytest.raises(PersonalConnectorUnavailable):
        await inventory_fixture.inventory().get(PersonalConnectorQuery(connector_id="capability-only"))


@pytest.mark.asyncio
async def test_inventory_projects_effective_description_without_internal_state(inventory_fixture: InventoryFixture) -> None:
    await inventory_fixture.descriptions.set(SetCapabilityDescriptionOverride(
        key=ConnectorCapabilityDescriptionKey(kind="downstream_mcp", connector_id="alpha"),
        description="Approved personal account capabilities", expected_revision=0,
    ))
    selected = await inventory_fixture.inventory().get(PersonalConnectorQuery(connector_id="alpha"))
    assert selected.capability_description == "Approved personal account capabilities"
    assert set(selected.model_dump()) == {
        "connector_id", "display_name", "capability_description", "enabled", "has_authorization",
    }


@pytest.mark.asyncio
async def test_disable_retains_authorization_and_disconnect_clears_only_current_owner(inventory_fixture: InventoryFixture) -> None:
    key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="alice"), connector_id="alpha")
    state = await inventory_fixture.stores.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert isinstance(state, PersonalConnection)
    await inventory_fixture.stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(
        key=key, expected_revision=state.revision, authorization=Authorized(authorization=SecretStr("token-canary")),
    ))
    disabled = await inventory_fixture.inventory().set_enabled(SetPersonalConnectorEnablement(connector_id="alpha", enabled=False))
    assert not disabled.enabled
    assert disabled.has_authorization
    assert "token-canary" not in disabled.model_dump_json()
    for subject, namespace in (("bob", "trusted"), ("alice", "other")):
        other = await inventory_fixture.inventory(subject, namespace).get(PersonalConnectorQuery(connector_id="alpha"))
        assert not other.enabled
        assert not other.has_authorization
    await inventory_fixture.inventory().disconnect(PersonalConnectorQuery(connector_id="alpha"))
    disconnected = await inventory_fixture.inventory().get(PersonalConnectorQuery(connector_id="alpha"))
    assert not disconnected.enabled
    assert not disconnected.has_authorization
