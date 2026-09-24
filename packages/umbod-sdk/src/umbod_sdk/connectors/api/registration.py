import base64
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from inspect import Parameter, signature
from typing import Annotated, get_args, get_origin

from jsonschema.validators import validator_for

from umbod_sdk.connectors.capability_description import validate_capability_description
from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.uploaded_file import UploadedFile

from umbod_sdk.connectors.api.definition import (
    AbsentConnectorValue,
    ConnectorDefinition,
    PresentConnectorValue,
    PromptDefinition,
    ResourceDefinition,
)
from umbod_sdk.connectors.output_schema import PresentConnectorToolOutputSchema
from umbod_sdk.connectors.api.parameters import (
    HIDDEN_PARAMETER_NAMES,
    prompt_parameter_descriptions,
    tool_parameter_descriptions,
    tool_parameters_schema,
)
from umbod_sdk.connectors.models import ConnectorConfigurationCheckResult
from umbod_sdk.connectors.types import ConnectorRegistration


def connector_registration(definition: ConnectorDefinition) -> ConnectorRegistration:
    validate_connector(definition)
    return {
        "id": definition.id,
        "display_name": definition.name,
        "tool_name_prefix": definition.id,
        "description": definition.description,
        "capability_description": validate_capability_description(
            definition.capability_description
        ),
        "icon_data_url": _icon_data_url(definition.icon),
        "extension": (
            definition.extension.value
            if isinstance(definition.extension, PresentConnectorValue)
            else {"source": "user-supplied"}
        ),
        "configuration_schema": definition.configuration,
        "configuration_check": _configuration_check(definition),
        "tool_descriptions": _tool_descriptions(definition),
        "prompt_descriptions": _prompt_descriptions(definition),
        "resource_descriptions": _resource_descriptions(definition),
    }


def _icon_data_url(
    icon: AbsentConnectorValue | PresentConnectorValue[Path],
) -> str | None:
    if isinstance(icon, AbsentConnectorValue):
        return None
    if icon.value.suffix.lower() != ".svg":
        raise ValueError("connector icon must be an SVG file")
    icon_bytes = icon.value.read_bytes()
    encoded_icon = base64.b64encode(icon_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_icon}"


def _tool_descriptions(definition: ConnectorDefinition) -> list[dict[str, object]]:
    return [
        {
            "operation_name": tool.operation_name,
            "description": tool.description,
            "parameters": tool_parameter_descriptions(tool),
            **(
                {
                    "output_schema_status": "present",
                    "output_schema": tool.output_schema.output_schema,
                }
                if isinstance(tool.output_schema, PresentConnectorToolOutputSchema)
                else {"output_schema_status": "absent"}
            ),
        }
        for tool in definition.tools
    ]


def _prompt_descriptions(definition: ConnectorDefinition) -> list[dict[str, object]]:
    return [
        {
            "name": prompt.name,
            "description": prompt.description,
            "parameters": prompt_parameter_descriptions(prompt),
        }
        for prompt in definition.prompts
    ]


def _resource_descriptions(definition: ConnectorDefinition) -> list[dict[str, object]]:
    return [
        {
            "uri_template": resource.uri_template,
            "name": resource.name,
            "description": resource.description,
            "parameters": resource.parameters,
        }
        for resource in definition.resources
    ]


def validate_connector(definition: ConnectorDefinition) -> None:
    validate_capability_description(definition.capability_description)
    if not isinstance(definition.configuration, type) or not issubclass(
        definition.configuration, Model
    ):
        raise ValueError("connector requires a configuration schema")
    if isinstance(definition.configuration_check, AbsentConnectorValue):
        raise ValueError("connector requires a configuration check")
    if not definition.tools and not definition.prompts and not definition.resources:
        raise ValueError("connector requires at least one documented capability")
    _validate_prompts(definition.prompts)
    _validate_resources(definition.resources)
    for tool in definition.tools:
        _validate_uploaded_file_declaration(tool.function)
        tool_parameter_descriptions(tool)
        tool_parameters_schema(tool)
        if isinstance(tool.output_schema, PresentConnectorToolOutputSchema):
            validator_for(tool.output_schema.output_schema).check_schema(
                tool.output_schema.output_schema
            )


def _validate_uploaded_file_declaration(function: Callable[..., object]) -> None:
    file_parameters: list[Parameter] = []
    for parameter in signature(function).parameters.values():
        annotation = parameter.annotation
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]
        if annotation is UploadedFile:
            file_parameters.append(parameter)
            continue
        if UploadedFile in get_args(annotation):
            raise ValueError("UploadedFile must be declared directly as one required parameter")
    if len(file_parameters) > 1:
        raise ValueError("file connector tools must declare exactly one UploadedFile parameter")
    if not file_parameters:
        return
    if file_parameters[0].default is not Parameter.empty:
        raise ValueError("UploadedFile parameter must be required and have no default")
    public_parameters = [
        parameter
        for parameter in signature(function).parameters.values()
        if parameter.name != "configuration"
    ]
    if public_parameters != file_parameters:
        raise ValueError(
            "file connector tools may expose only one required UploadedFile parameter; "
            "configuration is the only optional hidden parameter"
        )


def _validate_prompts(prompts: list[PromptDefinition]) -> None:
    seen_names: set[str] = set()
    for prompt in prompts:
        if not prompt.name or not prompt.description:
            raise ValueError("prompt declaration is missing required metadata")
        if prompt.name in seen_names:
            raise ValueError(f"duplicate prompt name: {prompt.name}")
        seen_names.add(prompt.name)
        prompt_parameter_descriptions(prompt)


def _validate_resources(resources: list[ResourceDefinition]) -> None:
    seen_uri_templates: set[str] = set()
    for resource in resources:
        if not resource.uri_template or not resource.name or not resource.description:
            raise ValueError("resource declaration is missing required metadata")
        if resource.uri_template in seen_uri_templates:
            raise ValueError(f"duplicate resource URI template: {resource.uri_template}")
        seen_uri_templates.add(resource.uri_template)
        _validate_resource_uri_template(
            resource.uri_template, signature(resource.function).parameters
        )


def _validate_resource_uri_template(uri_template: str, parameters: Mapping[str, Parameter]) -> None:
    if "://" not in uri_template or uri_template.startswith("://") or uri_template.endswith("://"):
        raise ValueError("resource requires a FastMCP-compatible URI template")
    public_parameter_names = set(parameters) - HIDDEN_PARAMETER_NAMES
    for parameter_name in re.findall(r"\{([^{}]+)\}", uri_template):
        if parameter_name not in public_parameter_names:
            raise ValueError(
                f"resource URI parameter is not accepted by function: {parameter_name}"
            )


def _configuration_check(
    definition: ConnectorDefinition,
) -> Callable[[Model], bool | ConnectorConfigurationCheckResult]:
    def check(configuration: Model) -> bool | ConnectorConfigurationCheckResult:
        configuration_check = definition.configuration_check
        if isinstance(configuration_check, AbsentConnectorValue):
            raise ValueError("connector requires a configuration check")
        validated_configuration = definition.configuration.model_validate(
            configuration.model_dump()
        )
        return configuration_check.value(validated_configuration)

    return check
