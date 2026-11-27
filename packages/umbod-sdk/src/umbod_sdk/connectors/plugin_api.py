from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any, TypedDict, Unpack, cast, overload

from pydantic_core import PydanticUndefined

from umbod_sdk.connectors.api.definition import (
    AbsentConnectorValue,
    ConnectorDefinition,
    PresentConnectorValue,
    prompt_decorator,
    resource_decorator,
    tool_decorator,
)
from umbod_sdk.connectors.api.manifest import validate_manifest_schemas
from umbod_sdk.connectors.api.registration import connector_registration
from umbod_sdk.connectors.declaration import Connector as ConnectorDeclaration
from umbod_sdk.connectors.models import ConnectorConfigurationCheckResult
from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.types import ConnectorRegistration, ConnectorToolOperation
from umbod_sdk.connectors.uploaded_file import UploadedFile


def _valid_configuration_check_result(
    cls: type[ConfigurationCheckResult],
) -> ConfigurationCheckResult:
    return cls(valid=True)


class _ConfigurationCheckDetails(TypedDict, total=False):
    field_messages: dict[str, str]


class _ConfigurationCheckMessageDetails(_ConfigurationCheckDetails):
    message: str


@overload
def _invalid_configuration_check_result(
    cls: type[ConfigurationCheckResult],
    **details: Unpack[_ConfigurationCheckDetails],
) -> ConfigurationCheckResult: ...


@overload
def _invalid_configuration_check_result(
    cls: type[ConfigurationCheckResult],
    message: str,
    **details: Unpack[_ConfigurationCheckDetails],
) -> ConfigurationCheckResult: ...


@overload
def _invalid_configuration_check_result(
    cls: type[ConfigurationCheckResult],
    **details: Unpack[_ConfigurationCheckMessageDetails],
) -> ConfigurationCheckResult: ...


def _invalid_configuration_check_result(
    cls: type[ConfigurationCheckResult],
    *args: object,
    **details: object,
) -> ConfigurationCheckResult:
    if len(args) > 1:
        raise TypeError("invalid() accepts at most one positional message argument")
    message = args[0] if args else cast(str | None, details.pop("message", None))
    field_messages = cast(dict[str, str], details.get("field_messages") or {})
    return cls(valid=False, message=message, field_messages=field_messages)


class ConfigurationCheckResult(ConnectorConfigurationCheckResult):
    invalid = classmethod(_invalid_configuration_check_result)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        field = cls.model_fields["valid"]
        default = field.default
        if isinstance(default, partial) and default.func is _valid_configuration_check_result and default.args == (cls,):
            field.default = PydanticUndefined
            cls.model_rebuild(force=True)


class _ValidConfigurationCheckResultDescriptor:
    @overload
    def __get__(
        self, instance: None, owner: type[ConfigurationCheckResult]
    ) -> Callable[[], ConfigurationCheckResult]: ...

    @overload
    def __get__(
        self, instance: ConfigurationCheckResult, owner: type[ConfigurationCheckResult]
    ) -> bool: ...

    def __get__(
        self, instance: ConfigurationCheckResult | None, owner: type[ConfigurationCheckResult]
    ) -> bool | Callable[[], ConfigurationCheckResult]:
        if instance is not None:
            return instance.__dict__["valid"]
        return partial(_valid_configuration_check_result, owner)


ConfigurationCheckResult.valid = _ValidConfigurationCheckResultDescriptor()


class _ConnectorMetadataMixin(ConnectorDeclaration):
    _definition: ConnectorDefinition
    _declared_metadata: dict[str, Any]

    def _set_declaration_metadata(self, metadata: dict[str, Any]) -> None:
        self._declared_metadata = metadata

    def _connector_metadata(self) -> Mapping[str, Any]:
        if self._uses_explicit_configuration():
            return self._declared_metadata
        return vars(self._definition)

    @property
    def id(self) -> str:
        return self._connector_metadata()["id"]

    @property
    def name(self) -> str:
        return self._connector_metadata()["name"]

    @property
    def description(self) -> str:
        return self._connector_metadata()["description"]

    @property
    def capability_description(self) -> str:
        return self._connector_metadata()["capability_description"]

    @property
    def configuration(self) -> type[Model] | dict[str, Any]:
        return self._connector_metadata()["configuration"]

    @property
    def extension(self) -> Mapping[str, object] | None:
        extension = self._connector_metadata().get("extension", AbsentConnectorValue())
        return extension.value if isinstance(extension, PresentConnectorValue) else None

    @property
    def icon(self) -> Path | None:
        icon = self._connector_metadata().get("icon", AbsentConnectorValue())
        return icon.value if isinstance(icon, PresentConnectorValue) else None


class _ConnectorIconOptions(TypedDict, total=False):
    icon: Path


class _ConnectorExtensionOptions(_ConnectorIconOptions):
    extension: Mapping[str, object]


class _PortableConnectorOptions(TypedDict, total=False):
    http_targets: dict[str, str]


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

    @overload
    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: dict[str, Any],
        **definition_options: Unpack[_PortableConnectorOptions],
    ) -> None: ...

    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: type[Model] | dict[str, Any],
        **definition_options: object,
    ) -> None:
        allowed_options = {"extension", "icon"}
        if isinstance(configuration, dict):
            allowed_options.add("http_targets")
        unknown_options = set(definition_options) - allowed_options
        if unknown_options:
            option = min(unknown_options)
            raise TypeError(
                f"ConnectorFacade.__init__() got an unexpected keyword argument '{option}'"
            )
        extension = cast(Mapping[str, object] | None, definition_options.get("extension"))
        super().__init__(
            id=id,
            name=name,
            description=description,
            capability_description=capability_description,
            configuration=configuration,
            **(definition_options if isinstance(configuration, dict) else {}),
        )
        if isinstance(configuration, dict):
            return
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

    def _register_configuration_check(self, function: Callable[..., Any]) -> None:
        if self._uses_explicit_configuration():
            super()._register_configuration_check(function)
            return
        self._definition.configuration_check = PresentConnectorValue(function)

    def tool(
        self, *, description: str, **options: Any
    ) -> Callable[[ConnectorToolOperation], ConnectorToolOperation]:
        if self._uses_explicit_configuration():
            return super().tool(description=description, **options)
        return tool_decorator(self._definition, description=description, options=options)

    def manifest(self) -> dict[str, Any]:
        return validate_manifest_schemas(super().manifest())

    def prompt(self, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return prompt_decorator(self._trusted_definition(), options=options)

    def resource(
        self, uri_template: str, **options: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return resource_decorator(self._trusted_definition(), uri_template, options=options)

    def _trusted_definition(self) -> ConnectorDefinition:
        if self._uses_explicit_configuration():
            raise ValueError(
                "trusted plugin registration requires a configuration Model; "
                "use manifest() for an explicit JSON Schema"
            )
        return self._definition

    def definition(self) -> ConnectorDefinition:
        return self._trusted_definition()

    def registration(self) -> ConnectorRegistration:
        return connector_registration(self._trusted_definition())


class Connector(ConnectorFacade):
    pass


__all__ = ["ConfigurationCheckResult", "Connector", "UploadedFile"]
