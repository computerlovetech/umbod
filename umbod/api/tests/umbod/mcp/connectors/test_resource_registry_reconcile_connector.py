from dataclasses import dataclass
from typing import Any

import pytest

from umbod.core.activation import ActivationStatus, CapabilityRef, InMemoryActivationStore
from umbod.mcp.connectors.resources.registry import RuntimeConnectorResourceRegistry
from umbod.proxies import Model


class ConfigModel(Model):
    token: str


@dataclass
class StubPublishingStore:
    published: bool

    async def is_published(self, connector_id: str) -> bool:
        return self.published


@dataclass
class StubConfigurationStore:
    configuration: Model | None

    async def get_current_configuration(self, connector_id: str) -> Model | None:
        return self.configuration


class RecordingLocalProvider:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def remove_template(self, uri_template: str) -> None:
        self.removed.append(uri_template)


class RecordingMcp:
    def __init__(self) -> None:
        self.local_provider = RecordingLocalProvider()
        self.registered: list[str] = []

    def resource(self, uri_template: str, **_kwargs: Any):
        def decorator(fn: Any) -> Any:
            self.registered.append(uri_template)
            return fn

        return decorator


@dataclass
class ResourceMapping:
    connector_id: str
    uri_template: str
    name: str
    description: str
    parameters: dict[str, Any]

    def read(self, uri: str) -> str:
        return uri


@pytest.mark.asyncio
async def test_resource_registry_reconcile_connector_registers_and_removes_by_activation() -> None:
    activations = InMemoryActivationStore()
    mcp = RecordingMcp()
    mapping = ResourceMapping(
        connector_id="weather",
        uri_template="weather://forecast/{city}",
        name="forecast",
        description="Forecast",
        parameters={},
    )
    registry = RuntimeConnectorResourceRegistry(
        mcp,  # type: ignore[arg-type]
        schemas={"weather": ConfigModel},
        connector_configuration_store=StubConfigurationStore(ConfigModel(token="secret")),
        connector_publishing_store=StubPublishingStore(True),
        activation_store=activations,
        connector_resource_mappings=[mapping],
    )

    await registry.reconcile_connector("weather")
    assert mcp.registered == []

    await activations.set_status(
        CapabilityRef(
            connector_kind="native",
            connector_id="weather",
            capability_kind="resource_template",
            capability_key="weather://forecast/{city}",
        ),
        ActivationStatus.ENABLED,
    )
    await registry.reconcile_connector("weather")
    assert mcp.registered == ["weather://forecast/{city}"]

    await activations.set_status(
        CapabilityRef(
            connector_kind="native",
            connector_id="weather",
            capability_kind="resource_template",
            capability_key="weather://forecast/{city}",
        ),
        ActivationStatus.DISABLED,
    )
    await registry.reconcile_connector("weather")
    assert mcp.local_provider.removed == ["weather://forecast/{city}"]
