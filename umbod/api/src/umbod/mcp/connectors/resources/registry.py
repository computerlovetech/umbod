from collections.abc import Callable, Mapping, Sequence
from inspect import Parameter, Signature
from typing import Any

from fastmcp import FastMCP

from umbod.core.activation import ActivationStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import (
    ConnectorPublishStateChanged,
    ConnectorPublishingStore,
)
from umbod.core.connectors.native.runtime import ConnectorResourceMapping
from umbod.proxies import Model

from umbod.mcp.connectors.resources.eligibility import (
    ConnectorResourceEligibilityContext,
    is_connector_resource_eligible,
)


class RuntimeConnectorResourceRegistry:
    def __init__(
        self,
        mcp: FastMCP,
        *,
        schemas: Mapping[str, type[Model]],
        connector_configuration_store: ConnectorCurrentConfigurationStore,
        connector_publishing_store: ConnectorPublishingStore,
        activation_store: ActivationStore,
        connector_resource_mappings: Sequence[ConnectorResourceMapping],
    ) -> None:
        self._mcp = mcp
        self._schemas = schemas
        self._connector_configuration_store = connector_configuration_store
        self._connector_publishing_store = connector_publishing_store
        self._activation_store = activation_store
        self._connector_resource_mappings = connector_resource_mappings
        self._registered_uri_templates_by_connector_id: dict[str, set[str]] = {}

    async def reconcile_all(self) -> None:
        for connector_id in self._connector_ids():
            await self.reconcile_connector(connector_id)

    async def reconcile_connector(self, connector_id: str) -> None:
        eligible_mappings = await self._eligible_mappings_for_connector(connector_id)
        eligible_uri_templates = {mapping.uri_template for mapping in eligible_mappings}
        registered_uri_templates = self._registered_uri_templates_by_connector_id.get(
            connector_id, set()
        )
        for mapping in eligible_mappings:
            if mapping.uri_template not in registered_uri_templates:
                self._mcp.resource(
                    mapping.uri_template,
                    name=getattr(mapping, "name", None),
                    description=getattr(mapping, "description", None),
                    meta=_resource_meta(mapping),
                )(_resource_reader(mapping))
                self._registered_uri_templates_by_connector_id.setdefault(connector_id, set()).add(
                    mapping.uri_template
                )
        for uri_template in registered_uri_templates - eligible_uri_templates:
            self._mcp.local_provider.remove_template(uri_template)
            self._registered_uri_templates_by_connector_id.setdefault(connector_id, set()).discard(
                uri_template
            )

    async def handle_publish_state_changed(self, event: ConnectorPublishStateChanged) -> None:
        await self.reconcile_connector(event.connector_id)

    def _connector_ids(self) -> set[str]:
        connector_ids: set[str] = set()
        for mapping in self._connector_resource_mappings:
            connector_id = getattr(mapping, "connector_id", None)
            if isinstance(connector_id, str):
                connector_ids.add(connector_id)
        return connector_ids

    async def _eligible_mappings_for_connector(
        self, connector_id: str
    ) -> list[ConnectorResourceMapping]:
        context = ConnectorResourceEligibilityContext(
            schemas=self._schemas,
            connector_configuration_store=self._connector_configuration_store,
            connector_publishing_store=self._connector_publishing_store,
            activation_store=self._activation_store,
        )
        mappings: list[ConnectorResourceMapping] = []
        seen_uri_templates: set[str] = set()
        for mapping in self._connector_resource_mappings:
            mapping_connector_id = getattr(mapping, "connector_id", None)
            if mapping_connector_id != connector_id:
                continue
            if mapping.uri_template in seen_uri_templates:
                continue
            if await is_connector_resource_eligible(
                connector_id=connector_id,
                uri_template=mapping.uri_template,
                context=context,
            ):
                mappings.append(mapping)
                seen_uri_templates.add(mapping.uri_template)
        return mappings


def _resource_meta(mapping: ConnectorResourceMapping) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "connector_id": getattr(mapping, "connector_id", None),
        "capability_kind": "resource_template",
        "capability_key": mapping.uri_template,
        "operation_name": mapping.uri_template,
    }
    parameters = getattr(mapping, "parameters", {})
    if parameters:
        meta["connector"] = {"parameters": parameters}
    return {key: value for key, value in meta.items() if value is not None}


def _resource_reader(mapping: ConnectorResourceMapping) -> Callable[..., Any]:
    read_operation = getattr(mapping, "read_operation", None)
    if callable(read_operation):
        return read_operation

    def reader(**arguments: str) -> Any:
        return mapping.read(_uri_from_arguments(mapping.uri_template, arguments))

    reader.__name__ = "read_connector_resource"
    reader.__annotations__ = {name: str for name in _template_argument_names(mapping.uri_template)}
    reader.__signature__ = Signature(
        parameters=[
            Parameter(name, Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
            for name in _template_argument_names(mapping.uri_template)
        ]
    )
    return reader


def _template_argument_names(uri_template: str) -> list[str]:
    return [
        part[1:-1]
        for part in uri_template.split("/")
        if part.startswith("{") and part.endswith("}")
    ]


def _uri_from_arguments(uri_template: str, arguments: Mapping[str, str]) -> str:
    parts: list[str] = []
    for part in uri_template.split("/"):
        if part.startswith("{") and part.endswith("}"):
            parts.append(arguments[part[1:-1]])
        else:
            parts.append(part)
    return "/".join(parts)
