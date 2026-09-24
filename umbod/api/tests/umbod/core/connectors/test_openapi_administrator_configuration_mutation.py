from types import SimpleNamespace
from typing import Any

import pytest

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.administrator.connector_configuration import (
    AdministratorPrincipal,
    CapabilityPermissionDesiredState,
    ConfigurationResult,
    ConnectorConfigurationMutationWriter,
    ConnectorDesiredState,
    ConnectorReference,
    ReadConnectorConfiguration,
    SetCapabilityActivation,
    SetCapabilityDescription,
    SetCapabilityInvocationPolicy,
    UpdateGroupPermissions,
    UpsertConnectorConfiguration,
)
from umbod.core.capabilities.descriptions.overrides import ConnectorCapabilityDescriptionKey
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
)
from umbod.core.capabilities.descriptions.stores.service import (
    ConnectorCapabilityDescriptionOverrideStoreService,
)
from umbod.core.connectors.openapi.administrator_configuration_mutation import (
    OpenApiAdministratorConfigurationMutation,
)
from umbod.core.invocation import (
    ConnectorInvocationPolicyKey,
    DatabaseConnectorInvocationPolicyStore,
)
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GROUP_TABLE,
)
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.core.persistence import DatabaseSession


class CatalogStore:
    async def list_connectors(self) -> tuple[Any, ...]:
        return (SimpleNamespace(connector_id="inventory"),)

    async def list_operation_summaries(self, connector_id: str) -> tuple[Any, ...]:
        return (SimpleNamespace(operation_id="listItems"),)


class UnusedResultReader:
    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        raise AssertionError("failed mutations must not read a success result")


class FailingPermissionMutation:
    def __init__(self, delegate: GroupPermissionStoreService) -> None:
        self._delegate = delegate

    async def update_group_permissions_in_session(
        self, session: DatabaseSession, request: Any
    ) -> None:
        await self._delegate.update_group_permissions_in_session(session, request)
        raise RuntimeError("injected persistence failure")


@pytest.mark.asyncio
async def test_mutation_port_rolls_back_prior_writes_when_persistence_fails() -> None:
    runtime = await prepared_inmemory_runtime()
    database = runtime.database
    activations = CapabilityActivationStoreService(database, CAPABILITY_ACTIVATION_STATE_TABLE)
    policies = DatabaseConnectorInvocationPolicyStore(database)
    descriptions = ConnectorCapabilityDescriptionOverrideStoreService(
        database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE
    )
    permissions = GroupPermissionStoreService(
        database,
        GROUP_TABLE,
        CONNECTOR_PERMISSION_TABLE,
        CAPABILITY_PERMISSION_TABLE,
    )
    mutation: ConnectorConfigurationMutationWriter = OpenApiAdministratorConfigurationMutation(
        database,
        CatalogStore(),
        UnusedResultReader(),
        descriptions,
        FailingPermissionMutation(permissions),
    )
    connector = ConnectorReference(connector_kind="openapi", connector_id="inventory")
    request = UpsertConnectorConfiguration(
        principal=AdministratorPrincipal(memberships=("umbod-administrators",)),
        connector=connector,
        desired_state=ConnectorDesiredState(
            operations=(
                SetCapabilityActivation(
                    operation="set_capability_activation",
                    capability_kind="tool",
                    capability_key="listItems",
                    activation_status="enabled",
                ),
                SetCapabilityInvocationPolicy(
                    operation="set_capability_invocation_policy",
                    capability_kind="tool",
                    capability_key="listItems",
                    mode="ask",
                    expected_revision=0,
                ),
                SetCapabilityDescription(
                    operation="set_capability_description",
                    description="Must roll back",
                    expected_revision=0,
                ),
                UpdateGroupPermissions(
                    operation="update_group_permissions",
                    group_id="engineering",
                    connector_status="enabled",
                    capabilities=(
                        CapabilityPermissionDesiredState(
                            capability_kind="tool",
                            capability_key="listItems",
                            status="enabled",
                        ),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        await mutation.upsert(request)

    activation = await activations.get_status(
        CapabilityRef("openapi", "inventory", "tool", "listItems")
    )
    policy = await policies.get(
        ConnectorInvocationPolicyKey("openapi", "inventory", "listItems")
    )
    description = await descriptions.get(
        ConnectorCapabilityDescriptionKey(kind="openapi", connector_id="inventory")
    )
    group_permissions = await permissions.list_group_permissions("engineering")

    assert activation == ActivationStatus.DISABLED
    assert policy is None
    assert description.revision == 0
    assert group_permissions.connector_ids == ()
    assert group_permissions.capabilities == ()
