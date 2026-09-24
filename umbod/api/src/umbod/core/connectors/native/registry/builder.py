from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel, ValidationError
from umbod.proxies import Model
from pydantic_core import PydanticUndefined

from umbod.core.connectors.native.models import (
    ConnectorConfigurationCheckResult,
    ConnectorMetadata,
)
from umbod.core.connectors.native.registry.domain import (
    ConnectorConfigurationCheck,
    ConnectorDefinition,
    ConnectorPromptArgumentDescription,
    ConnectorPromptCatalogDescription,
    ConnectorRegistration,
    ConnectorResourceCatalogDescription,
)
from umbod.core.connectors.native.tools.descriptions import connector_tool_descriptions_from_registration


def default_configuration_check(configuration: Model) -> ConnectorConfigurationCheckResult:
    return ConnectorConfigurationCheckResult(valid=True)


@runtime_checkable
class PromptArgumentDescription(Protocol):
    name: str
    description: str
    required: bool


def _parse_prompt_argument(argument: object) -> ConnectorPromptArgumentDescription:
    if isinstance(argument, Mapping):
        return ConnectorPromptArgumentDescription(
            name=str(argument["name"]),
            description=str(argument["description"]),
            required=bool(argument["required"]),
        )
    if isinstance(argument, PromptArgumentDescription):
        return ConnectorPromptArgumentDescription(
            name=argument.name,
            description=argument.description,
            required=argument.required,
        )
    raise ValueError("connector prompt argument description is invalid")


class ConnectorDefinitionBuilder:
    def __init__(self, registration: ConnectorRegistration, seen_ids: set[str]) -> None:
        self._metadata = self._parse_metadata(registration)
        if self._metadata.id in seen_ids:
            raise ValueError(f"duplicate connector id: {self._metadata.id}")
        seen_ids.add(self._metadata.id)
        self._tool_name_prefix = str(registration.get("tool_name_prefix", self._metadata.id))
        self._configuration_schema = self._parse_configuration_schema(
            registration, self._metadata.id
        )
        self._configuration_check = self._parse_configuration_check(registration)
        self._tool_descriptions = connector_tool_descriptions_from_registration(registration)
        self._prompt_descriptions = self._parse_prompt_descriptions(registration)
        self._resource_descriptions = self._parse_resource_descriptions(registration)

    @property
    def connector_id(self) -> str:
        return self._metadata.id

    def build(self, available: bool) -> ConnectorDefinition:
        return ConnectorDefinition(
            metadata=self._metadata,
            tool_name_prefix=self._tool_name_prefix,
            configuration_schema=self._configuration_schema,
            configuration_check=self._configuration_check,
            tool_descriptions=self._tool_descriptions,
            prompt_descriptions=self._prompt_descriptions,
            resource_descriptions=self._resource_descriptions,
            available=available,
        )

    def _parse_metadata(self, registration: ConnectorRegistration) -> ConnectorMetadata:
        try:
            return ConnectorMetadata.model_validate(registration)
        except ValidationError as error:
            raise ValueError("connector metadata validation failed") from error

    def _parse_configuration_schema(
        self,
        registration: ConnectorRegistration,
        connector_id: str,
    ) -> type[Model]:
        configuration_schema = registration.get("configuration_schema")
        if not (
            isinstance(configuration_schema, type) and issubclass(configuration_schema, BaseModel)
        ):
            raise ValueError(f"connector {connector_id} needs to have a configuration schema")
        schema = cast(type[Model], configuration_schema)
        defaulted_fields = [
            name
            for name, field_info in schema.model_fields.items()
            if field_info.default is not PydanticUndefined or field_info.default_factory is not None
        ]
        if defaulted_fields:
            raise ValueError(
                f"connector {connector_id} configuration schema must not define default values"
            )
        return schema

    def _parse_prompt_descriptions(
        self, registration: ConnectorRegistration
    ) -> tuple[ConnectorPromptCatalogDescription, ...]:
        descriptions = cast(
            Sequence[Mapping[str, object]], registration.get("prompt_descriptions", ())
        )
        return tuple(
            ConnectorPromptCatalogDescription(
                name=str(description["name"]),
                description=str(description["description"]),
                arguments=tuple(
                    _parse_prompt_argument(argument)
                    for argument in cast(
                        Sequence[object],
                        description.get("arguments", description.get("parameters", ())),
                    )
                ),
            )
            for description in descriptions
        )

    def _parse_resource_descriptions(
        self, registration: ConnectorRegistration
    ) -> tuple[ConnectorResourceCatalogDescription, ...]:
        descriptions = cast(
            Sequence[Mapping[str, object]], registration.get("resource_descriptions", ())
        )
        resources: list[ConnectorResourceCatalogDescription] = []
        for description in descriptions:
            uri = str(description.get("uri", description.get("uri_template", "")))
            explicit_kind = description.get("kind")
            kind = (
                "resource_template"
                if explicit_kind == "resource_template" or "{" in uri
                else "resource"
            )
            resources.append(
                ConnectorResourceCatalogDescription(
                    kind=kind,
                    name=str(description["name"]),
                    description=str(description["description"]),
                    uri=uri,
                )
            )
        return tuple(resources)

    def _parse_configuration_check(
        self, registration: ConnectorRegistration
    ) -> ConnectorConfigurationCheck:
        configuration_check = registration.get("configuration_check")
        if configuration_check is None:
            return default_configuration_check
        if not callable(configuration_check):
            raise ValueError("connector configuration check must be callable")
        return cast(ConnectorConfigurationCheck, configuration_check)
