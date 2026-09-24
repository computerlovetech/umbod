from dataclasses import dataclass

import pytest

from umbod.core.activation import ActivationStatus, CapabilityRef, InMemoryActivationStore
from umbod.mcp.connectors.prompts.eligibility import (
    ConnectorPromptEligibilityContext,
    is_connector_prompt_eligible,
)
from umbod.mcp.connectors.resources.eligibility import (
    ConnectorResourceEligibilityContext,
    is_connector_resource_eligible,
)
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


@pytest.mark.asyncio
async def test_native_prompt_eligibility_requires_activation() -> None:
    activations = InMemoryActivationStore()
    context = ConnectorPromptEligibilityContext(
        schemas={"weather": ConfigModel},
        connector_configuration_store=StubConfigurationStore(ConfigModel(token="secret")),
        connector_publishing_store=StubPublishingStore(True),
        activation_store=activations,
    )
    assert (
        await is_connector_prompt_eligible(
            connector_id="weather", prompt_name="forecast_prompt", context=context
        )
        is False
    )
    await activations.set_status(
        CapabilityRef(
            connector_kind="native",
            connector_id="weather",
            capability_kind="prompt",
            capability_key="forecast_prompt",
        ),
        ActivationStatus.ENABLED,
    )
    assert (
        await is_connector_prompt_eligible(
            connector_id="weather", prompt_name="forecast_prompt", context=context
        )
        is True
    )


@pytest.mark.asyncio
async def test_native_resource_eligibility_requires_activation() -> None:
    activations = InMemoryActivationStore()
    context = ConnectorResourceEligibilityContext(
        schemas={"weather": ConfigModel},
        connector_configuration_store=StubConfigurationStore(ConfigModel(token="secret")),
        connector_publishing_store=StubPublishingStore(True),
        activation_store=activations,
    )
    assert (
        await is_connector_resource_eligible(
            connector_id="weather",
            uri_template="data://weather/{city}",
            context=context,
        )
        is False
    )
    await activations.set_status(
        CapabilityRef(
            connector_kind="native",
            connector_id="weather",
            capability_kind="resource_template",
            capability_key="data://weather/{city}",
        ),
        ActivationStatus.ENABLED,
    )
    assert (
        await is_connector_resource_eligible(
            connector_id="weather",
            uri_template="data://weather/{city}",
            context=context,
        )
        is True
    )
