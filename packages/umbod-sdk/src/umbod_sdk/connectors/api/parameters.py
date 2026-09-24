from inspect import Parameter, signature
from typing import Annotated, Any, Protocol, get_args, get_origin

from pydantic import TypeAdapter
from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.uploaded_file import UploadedFile
from pydantic.fields import FieldInfo

from umbod_sdk.connectors.api.definition import PromptDefinition, ResourceDefinition, ToolDefinition


class ConnectorToolParameterDescription(Model):
    name: str
    description: str
    required: bool


HIDDEN_PARAMETER_NAMES = frozenset({"configuration"})
CapabilityDefinition = ToolDefinition | PromptDefinition | ResourceDefinition


def tool_parameter_descriptions(tool: ToolDefinition) -> list[ConnectorToolParameterDescription]:
    return create_parameter_metadata(tool).descriptions()


def prompt_parameter_descriptions(
    prompt: PromptDefinition,
) -> list[ConnectorToolParameterDescription]:
    return create_parameter_metadata(prompt).descriptions()


def tool_parameters_schema(tool: ToolDefinition) -> dict[str, Any]:
    return create_parameter_metadata(tool).schema()


def prompt_parameters_schema(prompt: PromptDefinition) -> dict[str, Any]:
    return create_parameter_metadata(prompt).schema()


def resource_parameters_schema(resource: ResourceDefinition) -> dict[str, Any]:
    return create_parameter_metadata(resource).schema()


def create_parameter_metadata(capability: CapabilityDefinition) -> "ToolParameterMetadata":
    description_resolvers: list[ParameterDescriptionResolver] = [
        OverrideParameterDescriptionResolver(),
        AnnotatedParameterDescriptionResolver(),
        FieldInfoParameterDescriptionResolver(),
        PydanticModelParameterDescriptionResolver(),
    ]
    return ToolParameterMetadata(
        capability=capability,
        parameters=capability_parameters(capability),
        parameter_describer=ToolParameterDescriber(description_resolvers),
        schema_factory=PydanticParameterSchemaFactory(),
    )


class ParameterDescriptionResolver(Protocol):
    def description(self, capability: CapabilityDefinition, parameter: Parameter) -> str | None: ...


class ParameterSchemaFactory(Protocol):
    def schema(self, parameter: Parameter) -> dict[str, Any]: ...


class ParameterDescriber(Protocol):
    def required_description(
        self, capability: CapabilityDefinition, parameter: Parameter
    ) -> str: ...


class ToolParameterMetadata:
    def __init__(
        self,
        capability: CapabilityDefinition,
        parameters: list[Parameter],
        parameter_describer: ParameterDescriber,
        schema_factory: ParameterSchemaFactory,
    ) -> None:
        self._capability = capability
        self._parameters = parameters
        self._parameter_describer = parameter_describer
        self._schema_factory = schema_factory

    def descriptions(self) -> list[ConnectorToolParameterDescription]:
        return [
            ConnectorToolParameterDescription(
                name=parameter.name,
                description=self._parameter_describer.required_description(
                    self._capability, parameter
                ),
                required=parameter.default is Parameter.empty,
            )
            for parameter in self._parameters
        ]

    def schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in self._parameters:
            parameter_schema = self._schema_factory.schema(parameter)
            parameter_schema["description"] = self._parameter_describer.required_description(
                self._capability, parameter
            )
            properties[parameter.name] = parameter_schema
            if parameter.default is Parameter.empty:
                required.append(parameter.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema


def capability_parameters(capability: CapabilityDefinition) -> list[Parameter]:
    return [
        parameter
        for parameter in signature(capability.function).parameters.values()
        if parameter.name not in HIDDEN_PARAMETER_NAMES
    ]


class ToolParameterDescriber:
    def __init__(self, resolvers: list[ParameterDescriptionResolver]) -> None:
        self._resolvers = resolvers

    def required_description(self, capability: CapabilityDefinition, parameter: Parameter) -> str:
        description = self.optional_description(capability, parameter)
        if not description:
            raise ValueError(f"capability parameter {parameter.name} is missing a description")
        return description

    def optional_description(
        self, capability: CapabilityDefinition, parameter: Parameter
    ) -> str | None:
        for resolver in self._resolvers:
            description = resolver.description(capability, parameter)
            if description:
                return description
        return None


class OverrideParameterDescriptionResolver:
    def description(self, capability: CapabilityDefinition, parameter: Parameter) -> str | None:
        return capability.parameters.get(parameter.name)


class AnnotatedParameterDescriptionResolver:
    def description(self, capability: CapabilityDefinition, parameter: Parameter) -> str | None:
        if get_origin(parameter.annotation) is not Annotated:
            return None
        for metadata in get_args(parameter.annotation)[1:]:
            if isinstance(metadata, FieldInfo) and metadata.description:
                return metadata.description
            if isinstance(metadata, str):
                return metadata
        return None


class FieldInfoParameterDescriptionResolver:
    def description(self, capability: CapabilityDefinition, parameter: Parameter) -> str | None:
        if isinstance(parameter.default, FieldInfo):
            return parameter.default.description
        return None


class PydanticModelParameterDescriptionResolver:
    def description(self, capability: CapabilityDefinition, parameter: Parameter) -> str | None:
        if isinstance(parameter.annotation, type) and issubclass(parameter.annotation, Model):
            return self._model_parameter_description(parameter.annotation)
        return None

    def _model_parameter_description(self, model: type[Model]) -> str:
        words = self._words_from_pascal_case(model.__name__)
        if words and words[-1] == "request":
            words[-1] = "parameters"
            if len(words) > 1 and words[-2].endswith("s"):
                words[-2] = words[-2][:-1]
        return f"{' '.join(words).capitalize()}."

    def _words_from_pascal_case(self, value: str) -> list[str]:
        words: list[str] = []
        current = ""
        for character in value:
            if character.isupper() and current:
                words.append(current.lower())
                current = character
            else:
                current += character
        if current:
            words.append(current.lower())
        return words


class PydanticParameterSchemaFactory:
    def schema(self, parameter: Parameter) -> dict[str, Any]:
        annotation = Any if parameter.annotation is Parameter.empty else parameter.annotation
        resolved_annotation = get_args(annotation)[0] if get_origin(annotation) is Annotated else annotation
        if resolved_annotation is UploadedFile:
            return {"type": "string", "format": "binary", "x-umbod-file-input": True}
        if isinstance(annotation, type) and issubclass(annotation, Model):
            return {
                "$ref": f"#/$defs/{annotation.__name__}",
                "$defs": {annotation.__name__: annotation.model_json_schema()},
            }
        schema = TypeAdapter(annotation).json_schema()
        if "$defs" in schema:
            return schema
        return dict(schema)
