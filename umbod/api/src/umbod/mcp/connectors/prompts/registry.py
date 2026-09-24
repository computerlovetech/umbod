from collections.abc import Mapping, Sequence

from fastmcp import FastMCP
from umbod.core.activation import ActivationStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import (
    ConnectorPublishStateChanged,
    ConnectorPublishingStore,
)
from umbod.core.connectors.native.runtime import ConnectorPromptMapping
from umbod.proxies import Model

from umbod.mcp.connectors.prompts.definition import FastMcpConnectorPromptRegistrar
from umbod.mcp.connectors.prompts.eligibility import (
    ConnectorPromptEligibilityContext,
    is_connector_prompt_eligible,
)
from umbod.mcp.connectors.prompts.naming import prompt_name


class RuntimeConnectorPromptRegistry:
    def __init__(
        self,
        mcp: FastMCP,
        *,
        schemas: Mapping[str, type[Model]],
        connector_configuration_store: ConnectorCurrentConfigurationStore,
        connector_publishing_store: ConnectorPublishingStore,
        activation_store: ActivationStore,
        connector_prompt_mappings: Sequence[ConnectorPromptMapping],
    ) -> None:
        self._mcp = mcp
        self._schemas = schemas
        self._connector_configuration_store = connector_configuration_store
        self._connector_publishing_store = connector_publishing_store
        self._activation_store = activation_store
        self._connector_prompt_mappings = connector_prompt_mappings
        self._registered_prompt_names_by_connector_id: dict[str, set[str]] = {}

    async def reconcile_all(self) -> None:
        for connector_id in self._connector_ids():
            await self.reconcile_connector(connector_id)

    async def reconcile_connector(self, connector_id: str) -> None:
        eligible_prompt_names = await self._eligible_prompt_names(connector_id)
        registered_prompt_names = self._registered_prompt_names_by_connector_id.get(
            connector_id, set()
        )
        for mapping in self._connector_prompt_mappings:
            name = prompt_name(mapping)
            if (
                mapping.connector_id == connector_id
                and name in eligible_prompt_names
                and name not in registered_prompt_names
            ):
                FastMcpConnectorPromptRegistrar().register(self._mcp, mapping)
                self._registered_prompt_names_by_connector_id.setdefault(connector_id, set()).add(
                    name
                )
        for name in registered_prompt_names - eligible_prompt_names:
            self._mcp.local_provider.remove_prompt(name)
            self._registered_prompt_names_by_connector_id.setdefault(connector_id, set()).discard(
                name
            )

    async def handle_publish_state_changed(self, event: ConnectorPublishStateChanged) -> None:
        await self.reconcile_connector(event.connector_id)

    def _connector_ids(self) -> set[str]:
        return {mapping.connector_id for mapping in self._connector_prompt_mappings}

    async def _eligible_prompt_names(self, connector_id: str) -> set[str]:
        context = ConnectorPromptEligibilityContext(
            schemas=self._schemas,
            connector_configuration_store=self._connector_configuration_store,
            connector_publishing_store=self._connector_publishing_store,
            activation_store=self._activation_store,
        )
        eligible_names: set[str] = set()
        for mapping in self._connector_prompt_mappings:
            if mapping.connector_id == connector_id and await is_connector_prompt_eligible(
                connector_id=mapping.connector_id,
                prompt_name=mapping.name,
                context=context,
            ):
                eligible_names.add(prompt_name(mapping))
        return eligible_names
