from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypedDict, Unpack, cast, overload

from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.uploaded_file import UploadedFile

from umbod_sdk.connectors.api.definition import (
    AbsentConnectorValue,
    ConnectorDefinition,
    PresentConnectorValue,
    prompt_decorator,
    resource_decorator,
    tool_decorator,
)
from umbod_sdk.connectors.api.registration import connector_registration
from umbod_sdk.connectors.models import ConnectorConfigurationCheckResult
from umbod_sdk.connectors.types import ConnectorRegistration, ConnectorToolOperation


def _valid_configuration_check_result(
    cls: type["ConfigurationCheckResult"],
) -> "ConfigurationCheckResult":
    return cls(valid=True)


class _ConfigurationCheckDetails(TypedDict, total=False):
    field_messages: dict[str, str]


class _ConfigurationCheckMessageDetails(_ConfigurationCheckDetails):
    message: str


@overload
def _invalid_configuration_check_result(
    cls: type["ConfigurationCheckResult"],
    **details: Unpack[_ConfigurationCheckDetails],
) -> "ConfigurationCheckResult": ...


@overload
def _invalid_configuration_check_result(
    cls: type["ConfigurationCheckResult"],
    message: str,
    **details: Unpack[_ConfigurationCheckDetails],
) -> "ConfigurationCheckResult": ...


@overload
def _invalid_configuration_check_result(
    cls: type["ConfigurationCheckResult"],
    **details: Unpack[_ConfigurationCheckMessageDetails],
) -> "ConfigurationCheckResult": ...


def _invalid_configuration_check_result(
    cls: type["ConfigurationCheckResult"],
    *args: object,
    **details: object,
) -> "ConfigurationCheckResult":
    if len(args) > 1:
        raise TypeError("invalid() accepts at most one positional message argument")
    message = args[0] if args else cast(str | None, details.pop("message", None))
    field_messages = cast(dict[str, str], details.get("field_messages") or {})
    return cls(valid=False, message=message, field_messages=field_messages)


class ConfigurationCheckResult(ConnectorConfigurationCheckResult):
    valid = classmethod(_valid_configuration_check_result)
    invalid = classmethod(_invalid_configuration_check_result)


class _ConnectorMetadataMixin:
    _definition: ConnectorDefinition

    @property
    def id(self) -> str:
        return self._definition.id

    @property
    def name(self) -> str:
        return self._definition.name

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def capability_description(self) -> str:
        return self._definition.capability_description

    @property
    def configuration(self) -> type[Model]:
        return self._definition.configuration

    @property
    def extension(self) -> Mapping[str, object] | None:
        extension = self._definition.extension
        return extension.value if isinstance(extension, PresentConnectorValue) else None

    @property
    def icon(self) -> Path | None:
        icon = self._definition.icon
        return icon.value if isinstance(icon, PresentConnectorValue) else None


class _ConnectorIconOptions(TypedDict, total=False):
    icon: Path


class _ConnectorExtensionOptions(_ConnectorIconOptions):
    extension: Mapping[str, object]


class ConnectorFacade(_ConnectorMetadataMixin):
    @overload
    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: type[Model],
        **definition_options: Unpack[_ConnectorIconOptions],
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: type[Model],
        **definition_options: Unpack[_ConnectorExtensionOptions],
    ) -> None: ...

    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: type[Model],
        **definition_options: object,
    ) -> None:
        unknown_options = set(definition_options) - {"extension", "icon"}
        if unknown_options:
            option = sorted(unknown_options)[0]
            raise TypeError(
                f"ConnectorFacade.__init__() got an unexpected keyword argument '{option}'"
            )
        extension = cast(Mapping[str, object] | None, definition_options.get("extension"))
        icon = cast(Path | None, definition_options.get("icon"))
        self._definition = ConnectorDefinition(
            id=id,
            name=name,
            description=description,
            capability_description=capability_description,
            configuration=configuration,
            icon=PresentConnectorValue(icon) if icon is not None else AbsentConnectorValue(),
            extension=(
                PresentConnectorValue(extension)
                if extension is not None
                else AbsentConnectorValue()
            ),
        )

    def configuration_check(
        self,
        function: Callable[..., bool | ConnectorConfigurationCheckResult],
    ) -> Callable[..., bool | ConnectorConfigurationCheckResult]:
        self._definition.configuration_check = PresentConnectorValue(function)
        return function

    def tool(
        self, *, description: str, **options: Any
    ) -> Callable[[ConnectorToolOperation], ConnectorToolOperation]:
        return tool_decorator(self._definition, description=description, options=options)

    def prompt(self, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return prompt_decorator(self._definition, options=options)

    def resource(
        self, uri_template: str, **options: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return resource_decorator(self._definition, uri_template, options=options)

    def definition(self) -> ConnectorDefinition:
        return self._definition

    def registration(self) -> ConnectorRegistration:
        return connector_registration(self._definition)


class Connector(ConnectorFacade):
    pass


__all__ = ["ConfigurationCheckResult", "Connector", "UploadedFile"]
