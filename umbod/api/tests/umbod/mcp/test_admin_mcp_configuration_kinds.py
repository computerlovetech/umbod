from pathlib import Path
from typing import Literal

import pytest
from fastmcp import Client, FastMCP

from messaging.models import MessagingEvent, StreamEvent
from tests.persistence_runtime import (
    prepared_inmemory_runtime,
    prepared_sqlite_runtime,
)
from umbod.core.messaging.stores.event_stream import (
    DatabaseEventStream,
    append_event_in_session,
)
from umbod.core.persistence import DatabaseSession
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.administrator.connector_configuration import (
    AdministratorConnectorConfiguration,
    AdministratorConnectorConfigurationService,
    AdministratorPrincipal,
    ConnectorReference,
)
from umbod.core.administrator.connector_configuration.catalog import (
    InMemoryConnectorConfigurationCatalog,
)
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
)
from umbod.core.capabilities.descriptions.stores.service import (
    ConnectorCapabilityDescriptionOverrideStoreService,
)
from umbod.core.administrator.connector_configuration.reader import (
    CatalogAdministratorConnectorConfigurationReader,
)
from umbod.core.administrator.connector_configuration.mutation import (
    CatalogAdministratorConfigurationMutation,
)
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GROUP_TABLE,
)
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.mcp.administrator.tools import AdministratorConnectorConfigurationTools

ConnectorKind = Literal["native", "openapi", "downstream_mcp"]


def principal(membership_claim: str) -> AdministratorPrincipal:
    return AdministratorPrincipal(memberships=("umbod-administrators",))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "openapi", "downstream_mcp"])
@pytest.mark.parametrize("backend", ["inmemory", "sqlite"])
async def test_mcp_configuration_roundtrip_conflict_and_isolation(
    kind: ConnectorKind,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    tmp_path: Path,
) -> None:
    runtime = (
        await prepared_inmemory_runtime()
        if backend == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "configuration.sqlite")
    )
    database = runtime.database
    event_stream = DatabaseEventStream(database)
    connectors = tuple(
        ConnectorReference(connector_kind=kind, connector_id=identifier)
        for identifier in ("inventory", "other")
    )
    capabilities = tuple(
        CapabilityIdentity(
            connector_kind=kind,
            connector_id=connector.connector_id,
            capability_kind=capability_kind,
            capability_key=key,
        )
        for connector in connectors
        for capability_kind, key in (
            ("tool", "listItems"),
            ("prompt", "summary"),
            ("resource", "data://inventory"),
            ("resource_template", "data://inventory/{item}"),
        )
    )
    catalog = InMemoryConnectorConfigurationCatalog(connectors, capabilities)
    activations = CapabilityActivationStoreService(
        database, CAPABILITY_ACTIVATION_STATE_TABLE
    )
    policies = DatabaseConnectorInvocationPolicyStore(database)
    descriptions = ConnectorCapabilityDescriptionOverrideStoreService(
        database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE
    )
    permissions = GroupPermissionStoreService(
        database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE
    )
    reader = CatalogAdministratorConnectorConfigurationReader(
        catalog, activations, policies, descriptions, permissions
    )
    configuration: AdministratorConnectorConfiguration = (
        AdministratorConnectorConfigurationService(
            reader,
            CatalogAdministratorConfigurationMutation(
                database, catalog, reader, descriptions, permissions
            ),
        )
    )
    monkeypatch.setattr(
        "umbod.mcp.administrator.tools.current_administrator_principal", principal
    )
    tools = AdministratorConnectorConfigurationTools(configuration, "groups")
    server = FastMCP("configuration-test")
    server.tool(tools.read_connector_configuration)
    server.tool(tools.upsert_connector_configuration)
    target = {"connector_kind": kind, "connector_id": "inventory"}
    operations = [
        {
            "operation": "set_capability_activation",
            "capability_kind": "tool",
            "capability_key": "listItems",
            "activation_status": "disabled",
        },
        {
            "operation": "set_capability_invocation_policy",
            "capability_kind": "tool",
            "capability_key": "listItems",
            "mode": "ask",
            "expected_revision": 0,
        },
        {
            "operation": "set_capability_description",
            "description": "Inventory access",
            "expected_revision": 0,
        },
        {
            "operation": "set_capability_activation",
            "capability_kind": "prompt",
            "capability_key": "summary",
            "activation_status": "enabled",
        },
        {
            "operation": "update_group_permissions",
            "group_id": "engineering",
            "connector_status": "enabled",
            "capabilities": [
                {
                    "capability_kind": "prompt",
                    "capability_key": "summary",
                    "status": "enabled",
                }
            ],
        },
    ]
    async with Client(server) as client:
        result = await client.call_tool(
            "upsert_connector_configuration",
            {**target, "desired_state": {"operations": operations}},
        )
        state = result.structured_content
        events = await event_stream.list_after(0, 100)
        assert [event.event.event_type for event in events] == [
            "connector.invocation_policy.changed",
            "connector.capability_activation.changed",
            "connector.capability_description_override.changed",
            "mcp.group_permission.changed",
            "mcp.group_permission.changed",
        ]
        assert events[0].event.metadata == {
            "connector_kind": kind, "connector_id": "inventory",
            "operation_name": "listItems", "mode": "ask", "revision": "1",
        }
        assert events[1].event.metadata == {
            "connector_kind": kind, "connector_id": "inventory",
            "capability_kind": "prompt", "capability_key": "summary",
        }
        assert events[2].event.metadata == {
            "connector_kind": kind, "connector_id": "inventory",
            "action": "set", "revision": "1",
        }
        assert events[3].event.metadata == {
            "group_id": "engineering", "action": "grant",
            "target_kind": "connector", "connector_id": "inventory",
        }
        assert events[4].event.metadata == {
            "group_id": "engineering", "action": "grant",
            "target_kind": "prompt", "connector_id": "inventory",
            "capability_kind": "prompt", "capability_key": "summary",
        }
        assert state["connector"] == target
        assert state["capabilities"][0]["activation_status"] == "disabled"
        assert state["capabilities"][0]["invocation_policy"] == {
            "mode": "ask",
            "revision": 1,
        }
        assert all(
            capability["invocation_policy"] is None
            for capability in state["capabilities"][1:]
        )
        assert state["group_permissions"][0]["capabilities"][1]["status"] == "enabled"
        assert (
            await client.call_tool("read_connector_configuration", target)
        ).structured_content == state
        other = await client.call_tool(
            "read_connector_configuration", {**target, "connector_id": "other"}
        )
        assert other.structured_content["capability_description"] == {
            "state": "system",
            "revision": 0,
        }
        assert (
            other.structured_content["capabilities"][0]["invocation_policy"]["revision"]
            == 0
        )
        conflict_operations = [
            {
                "operation": "set_capability_activation",
                "capability_kind": "tool",
                "capability_key": "listItems",
                "activation_status": "enabled",
            },
            operations[1],
        ]
        conflict = await client.call_tool(
            "upsert_connector_configuration",
            {**target, "desired_state": {"operations": conflict_operations}},
            raise_on_error=False,
        )
        assert conflict.is_error
        assert await event_stream.list_after(0, 100) == events
        assert (
            await client.call_tool("read_connector_configuration", target)
        ).structured_content == state
        operations[1]["expected_revision"] = 1
        operations[2]["expected_revision"] = 1
        repeated = await client.call_tool(
            "upsert_connector_configuration",
            {**target, "desired_state": {"operations": operations}},
        )
        assert repeated.structured_content == state
        assert await event_stream.list_after(0, 100) == events
        reverse_operations = [
            {
                "operation": "set_capability_invocation_policy",
                "capability_kind": "tool", "capability_key": "listItems",
                "mode": "direct", "expected_revision": 1,
            },
            {
                "operation": "set_capability_activation",
                "capability_kind": "prompt", "capability_key": "summary",
                "activation_status": "disabled",
            },
            {
                "operation": "use_system_capability_description",
                "expected_revision": 1,
            },
            {
                "operation": "update_group_permissions",
                "group_id": "engineering", "connector_status": "disabled",
                "capabilities": [{
                    "capability_kind": "prompt", "capability_key": "summary",
                    "status": "disabled",
                }],
            },
        ]

        async def append_then_fail(
            session: DatabaseSession, event: MessagingEvent
        ) -> StreamEvent:
            saved = await append_event_in_session(session, event)
            if event.event_type == "mcp.group_permission.changed":
                raise RuntimeError("Event persistence failed")
            return saved

        with monkeypatch.context() as rollback_patch:
            rollback_patch.setattr(
                "umbod.core.administrator.connector_configuration.mutation.append_event_in_session",
                append_then_fail,
            )
            failed = await client.call_tool(
                "upsert_connector_configuration",
                {**target, "desired_state": {"operations": reverse_operations}},
                raise_on_error=False,
            )
            assert failed.is_error
        assert await event_stream.list_after(0, 100) == events
        assert (
            await client.call_tool("read_connector_configuration", target)
        ).structured_content == state
        wrong_kind = await client.call_tool(
            "upsert_connector_configuration",
            {
                **target,
                "desired_state": {
                    "operations": [
                        {
                            "operation": "set_capability_invocation_policy",
                            "capability_kind": "prompt",
                            "capability_key": "summary",
                            "mode": "ask",
                            "expected_revision": 0,
                        }
                    ]
                },
            },
            raise_on_error=False,
        )
        assert wrong_kind.is_error
        wrong_key = await client.call_tool(
            "upsert_connector_configuration",
            {
                **target,
                "desired_state": {
                    "operations": [
                        {
                            "operation": "set_capability_activation",
                            "capability_kind": "resource",
                            "capability_key": "summary",
                            "activation_status": "enabled",
                        }
                    ]
                },
            },
            raise_on_error=False,
        )
        assert wrong_key.is_error
        assert await event_stream.list_after(0, 100) == events
        assert (
            await client.call_tool("read_connector_configuration", target)
        ).structured_content == state
        await client.call_tool(
            "upsert_connector_configuration",
            {**target, "desired_state": {"operations": reverse_operations}},
        )
        reversed_events = await event_stream.list_after(events[-1].sequence, 100)
        assert [event.event.event_type for event in reversed_events] == [
            event.event.event_type for event in events
        ]
        assert reversed_events[0].event.metadata["mode"] == "direct"
        assert reversed_events[0].event.metadata["revision"] == "2"
        assert reversed_events[2].event.metadata["action"] == "clear"
        assert reversed_events[2].event.metadata["revision"] == "2"
        assert all(
            event.event.metadata["action"] == "revoke"
            for event in reversed_events[3:]
        )
