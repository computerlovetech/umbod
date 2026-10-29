from collections import Counter
from datetime import UTC, datetime

from tests.umbod.rest.mcp_permissions.assignable_support import (
    AdminPermissionHttp,
    read_assignable_targets,
)
from umbod.core.activation import ActivationStatus, CapabilityActivationState, CapabilityRef
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.capabilities import CapabilityKind
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredPrompt,
    DiscoveredToolWithoutOutputSchema,
    NoAuthConnectorDefinition,
    OAuthConnectorDefinition,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_DEFINITION_TABLE,
    TOOL_CATALOG_TABLE,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
)
from umbod.core.connectors.openapi.stores.schema import CONNECTOR_TABLE
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.rest.factories import ConnectorApiDependencyFactories


async def seed_shared_capabilities(
    factories: ConnectorApiDependencyFactories,
    connector_id: str,
    keys: tuple[str, ...],
    statuses: tuple[tuple[CapabilityKind, str, ActivationStatus], ...],
    include_prompts: bool,
) -> None:
    definitions = factories.downstream_mcp_definition_store.create()
    await definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
        connector_id=connector_id,
        display_name=connector_id.title(),
        endpoint_url="https://example.invalid/mcp",
    )))
    catalogs = factories.downstream_mcp_catalog_store.create()
    await catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id=connector_id,
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        tools=tuple(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id=connector_id, downstream_name=key),
            title=f"Tool {key}", description=key, input_schema={"type": "object"},
        ) for key in keys),
        prompts=tuple(DiscoveredPrompt(
            name=key, title=f"Prompt {key}", description=key,
        ) for key in keys) if include_prompts else (),
    )))
    publishing = await factories.connector_publishing_store.create()
    await publishing.publish_connector(connector_id)
    activation = await factories.capability_activation_store.create()
    await activation.set_statuses(tuple(CapabilityActivationState(
        ref=CapabilityRef(
            connector_kind="downstream_mcp", connector_id=connector_id,
            capability_kind=kind, capability_key=key,
        ),
        activation_status=status,
    ) for kind, key, status in statuses))


async def seed_personal_definitions(
    factories: ConnectorApiDependencyFactories, connector_ids: tuple[str, ...],
) -> None:
    definitions = factories.downstream_mcp_definition_store.create()
    publishing = await factories.connector_publishing_store.create()
    for connector_id in connector_ids:
        await definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
            connector_id=connector_id, display_name=connector_id.title(),
            endpoint_url="https://example.invalid/mcp", authorization_mode="personal",
        )))
        await publishing.publish_connector(connector_id)


async def withdraw_personal_publication(
    factories: ConnectorApiDependencyFactories, connector_id: str,
) -> None:
    publishing = await factories.connector_publishing_store.create()
    await publishing.unpublish_connector(connector_id)


def test_empty_assignable_inventory_does_not_read_publication_or_activation(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, _, counts = admin_permission_http

    targets = read_assignable_targets(client, counts)

    assert targets.model_dump() == {"connectors": [], "capabilities": []}
    assert counts.reads == Counter({
        CONNECTOR_TABLE.name: 1,
        CONNECTOR_DEFINITION_TABLE.name: 1,
    })
    assert counts.sessions == 2


def test_personal_targets_without_catalogues_use_batched_publication_and_no_activation(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    connector_ids = ("personal-000", "personal-001")
    client.portal.call(seed_personal_definitions, factories, connector_ids)

    targets = read_assignable_targets(client, counts)

    assert targets.model_dump() == {
        "connectors": [
            {"connector_id": connector_id, "display_name": connector_id.title()}
            for connector_id in connector_ids
        ],
        "capabilities": [],
    }
    assert counts.reads == Counter({
        CONNECTOR_TABLE.name: 1,
        CONNECTOR_DEFINITION_TABLE.name: 1,
        TOOL_CATALOG_TABLE.name: 2,
        PUBLICATION_STATE_TABLE.name: 1,
    })
    assert counts.sessions == 5

    client.portal.call(withdraw_personal_publication, factories, connector_ids[0])

    withdrawn_targets = read_assignable_targets(client, counts)

    assert withdrawn_targets.model_dump() == {
        "connectors": [
            {"connector_id": connector_id, "display_name": connector_id.title()}
            for connector_id in connector_ids[1:]
        ],
        "capabilities": [],
    }
    assert counts.reads[PUBLICATION_STATE_TABLE.name] == 1
    assert counts.reads[CAPABILITY_ACTIVATION_STATE_TABLE.name] == 0


def test_activation_snapshot_distinguishes_capability_kinds_with_the_same_key(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_capabilities, factories, "shared", ("a", "b", "c"), (
        ("tool", "a", ActivationStatus.ENABLED),
        ("prompt", "a", ActivationStatus.DISABLED),
        ("tool", "b", ActivationStatus.DISABLED),
        ("prompt", "b", ActivationStatus.ENABLED),
        ("prompt", "c", ActivationStatus.ENABLED),
    ), True)

    targets = read_assignable_targets(client, counts)

    assert targets.model_dump() == {
        "connectors": [{"connector_id": "shared", "display_name": "Shared"}],
        "capabilities": [
            {
                "connector_id": "shared", "capability_kind": kind,
                "capability_key": key, "display_name": title,
            }
            for kind, key, title in (
                ("prompt", "b", "Prompt b"),
                ("prompt", "c", "Prompt c"),
                ("tool", "a", "Tool a"),
            )
        ],
    }
    assert counts.reads[PUBLICATION_STATE_TABLE.name] == 1
    assert counts.reads[CAPABILITY_ACTIVATION_STATE_TABLE.name] == 1
    assert counts.sessions == 4


def test_shared_connectors_combine_state_reads_and_preserve_sorted_targets(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_capabilities, factories, "zulu", ("read", "write"), (
        ("tool", "read", ActivationStatus.DISABLED),
        ("tool", "write", ActivationStatus.ENABLED),
    ), False)
    client.portal.call(seed_shared_capabilities, factories, "alpha", ("write", "read"), (
        ("tool", "read", ActivationStatus.ENABLED),
        ("tool", "write", ActivationStatus.DISABLED),
    ), False)

    targets = read_assignable_targets(client, counts)

    assert targets.model_dump() == {
        "connectors": [
            {"connector_id": "alpha", "display_name": "Alpha"},
            {"connector_id": "zulu", "display_name": "Zulu"},
        ],
        "capabilities": [
            {
                "connector_id": connector_id, "capability_kind": "tool",
                "capability_key": key, "display_name": f"Tool {key}",
            }
            for connector_id, key in (("alpha", "read"), ("zulu", "write"))
        ],
    }
    assert counts.reads == Counter({
        CONNECTOR_TABLE.name: 1,
        CONNECTOR_DEFINITION_TABLE.name: 1,
        TOOL_CATALOG_TABLE.name: 2,
        PUBLICATION_STATE_TABLE.name: 1,
        CAPABILITY_ACTIVATION_STATE_TABLE.name: 1,
    })
    assert counts.sessions == 5
