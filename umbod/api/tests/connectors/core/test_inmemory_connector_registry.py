from umbod_sdk.connectors.proxies import Model

from umbod.core.connectors.native.registry.domain import (
    ConnectorDefinitionFilter,
    ConnectorRegistry,
)
from umbod.core.connectors.native.registry.inmemory import InMemoryConnectorRegistry


class EmptyConfiguration(Model):
    pass


def test_registry_exposes_only_explicitly_available_connectors() -> None:
    registry: ConnectorRegistry = InMemoryConnectorRegistry(
        [
            {
                "id": "available-connector",
                "display_name": "Available Connector",
                "capability_description": "Access connector capabilities.",
                "description": "Available connector",
                "extension": {"source": "built-in"},
                "configuration_schema": EmptyConfiguration,
            },
            {
                "id": "registered-connector",
                "display_name": "Registered Connector",
                "capability_description": "Access connector capabilities.",
                "description": "Registered connector",
                "extension": {"source": "built-in"},
                "configuration_schema": EmptyConfiguration,
            },
        ],
        ["available-connector"],
    )

    connector_ids = [
        connector.metadata.id
        for connector in registry.list_connector_definitions(ConnectorDefinitionFilter())
    ]

    assert connector_ids == ["available-connector"]
    assert (
        registry.get_connector_definition("registered-connector", ConnectorDefinitionFilter())
        is None
    )


def test_registry_accepts_explicit_registered_availability() -> None:
    registry: ConnectorRegistry = InMemoryConnectorRegistry(
        [
            {
                "id": "registered-connector",
                "display_name": "Registered Connector",
                "capability_description": "Access connector capabilities.",
                "description": "Registered connector",
                "extension": {"source": "built-in"},
                "configuration_schema": EmptyConfiguration,
            }
        ],
        [],
    )

    connector_ids = [
        connector.metadata.id
        for connector in registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="registered")
        )
    ]

    assert connector_ids == ["registered-connector"]
    assert (
        registry.get_connector_definition(
            "registered-connector", ConnectorDefinitionFilter(availability="registered")
        )
        is not None
    )


def test_registry_rejects_unknown_available_connector_ids() -> None:
    try:
        InMemoryConnectorRegistry(
            [
                {
                    "id": "installed-connector",
                    "display_name": "Installed Connector",
                    "capability_description": "Access connector capabilities.",
                    "description": "Installed connector",
                    "extension": {"source": "built-in"},
                    "configuration_schema": EmptyConfiguration,
                }
            ],
            ["unknown-connector"],
        )
    except ValueError as error:
        assert str(error) == (
            "unknown available connector ids: unknown-connector; "
            "installed connector ids: installed-connector"
        )
    else:
        raise AssertionError("Expected unknown connector availability to be rejected")
