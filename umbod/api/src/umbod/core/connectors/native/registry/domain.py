from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from umbod.proxies import Model

from umbod.core.connectors.native.models import (
    ConnectorConfigurationCheckResult,
    ConnectorMetadata,
)
from umbod.core.connectors.native.tools.descriptions import ConnectorToolDescriptionState

ConnectorRegistration = Mapping[str, object]
ConnectorConfigurationCheck = Callable[[Model], bool | ConnectorConfigurationCheckResult]
ConnectorAvailabilityFilter = Literal["available", "registered"]


class ConnectorDefinitionFilter(Model):
    availability: ConnectorAvailabilityFilter = "available"


@dataclass(frozen=True)
class ConnectorPromptArgumentDescription:
    name: str
    description: str
    required: bool


@dataclass(frozen=True)
class ConnectorPromptCatalogDescription:
    name: str
    description: str
    arguments: Sequence[ConnectorPromptArgumentDescription]


@dataclass(frozen=True)
class ConnectorResourceCatalogDescription:
    kind: Literal["resource", "resource_template"]
    name: str
    description: str
    uri: str


@dataclass(frozen=True)
class ConnectorDefinition:
    metadata: ConnectorMetadata
    tool_name_prefix: str
    configuration_schema: type[Model]
    configuration_check: ConnectorConfigurationCheck
    tool_descriptions: Mapping[str, ConnectorToolDescriptionState]
    prompt_descriptions: Sequence[ConnectorPromptCatalogDescription]
    resource_descriptions: Sequence[ConnectorResourceCatalogDescription]
    available: bool


class ConnectorRegistry(Protocol):
    def list_connector_definitions(
        self,
        filters: ConnectorDefinitionFilter,
    ) -> list[ConnectorDefinition]: ...

    def get_connector_definition(
        self,
        connector_id: str,
        filters: ConnectorDefinitionFilter,
    ) -> ConnectorDefinition | None: ...

    def check_configuration(
        self,
        connector_id: str,
        configuration: Model,
    ) -> ConnectorConfigurationCheckResult: ...
