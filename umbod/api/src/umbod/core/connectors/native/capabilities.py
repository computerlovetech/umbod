from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from inspect import Parameter, Signature, signature
from typing import Annotated, Any, Protocol

from pydantic import Field, TypeAdapter, ValidationError
from umbod.proxies import Model

from umbod.core.capabilities.catalog import (
    CapabilityIdentityConflictError,
    CapabilityNotFoundError,
)
from umbod.core.capabilities.domain import (
    AbsentCapabilityOutputSchema,
    CapabilityIdentity,
    CapabilityKind,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.native.registry.domain import (
    ConnectorDefinition,
    ConnectorDefinitionFilter,
    ConnectorPromptCatalogDescription,
    ConnectorRegistry,
    ConnectorResourceCatalogDescription,
)
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.connectors.native.tools.descriptions import ConnectorToolDescriptionState, ConnectorToolParameterDescription
from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.capabilities.tools.output_schema import PresentConnectorToolOutputSchema
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState


class ConnectorToolRuntimeStateReader(Protocol):
    def get_runtime_state(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None: ...


@dataclass(frozen=True)
class NativeCapabilityBinding:
    capability: NormalizedCapability
    mapping: ConnectorToolMapping | None
    public_tool_name: str


class NativeCapabilityCatalog:
    def __init__(self, bindings: Sequence[NativeCapabilityBinding]) -> None:
        self._bindings = tuple(bindings)
        self._by_identity = {binding.capability.identity: binding for binding in bindings}
        self._by_public_name = {
            binding.public_tool_name: binding
            for binding in bindings
            if binding.capability.identity.capability_kind == "tool"
        }
        if len(self._by_identity) != len(bindings):
            raise CapabilityIdentityConflictError(_duplicate_identity(bindings))

    @classmethod
    def from_mappings(cls, mappings: Sequence[ConnectorToolMapping]) -> "NativeCapabilityCatalog":
        return cls(tuple(_binding_from_mapping(mapping) for mapping in mappings))

    @classmethod
    def from_operation_names(
        cls, connector_tools: Mapping[str, Sequence[str]]
    ) -> "NativeCapabilityCatalog":
        return cls(
            tuple(
                _binding_from_operation_name(connector_id, operation_name)
                for connector_id, operation_names in connector_tools.items()
                for operation_name in operation_names
            )
        )

    @classmethod
    def from_registry(cls, registry: ConnectorRegistry) -> "NativeCapabilityCatalog":
        definitions = registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="available")
        )
        return cls(
            tuple(
                binding
                for definition in definitions
                for binding in _bindings_from_definition(definition)
            )
        )

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        return tuple(binding.capability for binding in self._bindings)

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        return self.resolve_binding(identity).capability

    def resolve_binding(self, identity: CapabilityIdentity) -> NativeCapabilityBinding:
        try:
            return self._by_identity[identity]
        except KeyError as error:
            raise CapabilityNotFoundError(identity) from error

    def resolve_public_name(self, public_tool_name: str) -> NativeCapabilityBinding | None:
        return self._by_public_name.get(public_tool_name)

    def connector_ids(self) -> frozenset[str]:
        return frozenset(
            binding.capability.identity.connector_id for binding in self._bindings
        )

    def replace_connector_operations(
        self, connector_id: str, operation_names: Sequence[str]
    ) -> None:
        retained = tuple(
            binding
            for binding in self._bindings
            if binding.capability.identity.connector_id != connector_id
            or binding.capability.identity.capability_kind != "tool"
        )
        replacements = tuple(
            _binding_from_operation_name(connector_id, operation_name)
            for operation_name in operation_names
        )
        self.__init__(retained + replacements)


class NativeCapabilityActivation:
    def __init__(self, runtime_states: ConnectorToolRuntimeStateReader | None) -> None:
        self._runtime_states = runtime_states

    async def is_enabled(self, identity: CapabilityIdentity) -> bool:
        if self._runtime_states is None:
            return True
        state = self._runtime_states.get_runtime_state(
            ConnectorToolRef(identity.connector_id, identity.capability_key)
        )
        return state is not None and state.status == "enabled"


class NativeCapabilityReadiness:
    def __init__(
        self,
        schemas: Mapping[str, type[Model]],
        configurations: ConnectorCurrentConfigurationStore,
    ) -> None:
        self._schemas = schemas
        self._configurations = configurations

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        schema = self._schemas.get(identity.connector_id)
        if schema is None:
            return False
        configuration = await self._configurations.get_current_configuration(
            identity.connector_id
        )
        if configuration is None:
            return False
        try:
            schema.model_validate(configuration.model_dump())
        except ValidationError:
            return False
        return True


def _binding_from_operation_name(
    connector_id: str, operation_name: str
) -> NativeCapabilityBinding:
    capability = _capability(
        _NativeCapabilityFields(
            connector_id,
            operation_name,
            operation_name,
            operation_name,
            {"properties": {}, "type": "object"},
            AbsentCapabilityOutputSchema(),
        )
    )
    return NativeCapabilityBinding(
        capability,
        None,
        mangle_public_tool_name(connector_id, operation_name),
    )


def _binding_from_mapping(mapping: ConnectorToolMapping) -> NativeCapabilityBinding:
    capability = _capability(
        _NativeCapabilityFields(
            mapping.connector_id,
            mapping.operation_name,
            mapping.operation_name,
            mapping.description,
            _mapping_input_schema(mapping),
            _mapping_output_schema(mapping),
        )
    )
    prefix = getattr(mapping, "tool_name_prefix", "") or mapping.connector_id
    return NativeCapabilityBinding(
        capability,
        mapping,
        mangle_public_tool_name(prefix, mapping.operation_name),
    )


def _bindings_from_definition(definition: ConnectorDefinition) -> tuple[NativeCapabilityBinding, ...]:
    tools = tuple(
        _binding_from_description(definition, description)
        for description in definition.tool_descriptions.values()
    )
    prompts = tuple(
        _binding_from_prompt(definition, prompt) for prompt in definition.prompt_descriptions
    )
    resources = tuple(
        _binding_from_resource(definition, resource)
        for resource in definition.resource_descriptions
    )
    return tools + prompts + resources


def _binding_from_description(
    definition: ConnectorDefinition, description: ConnectorToolDescriptionState
) -> NativeCapabilityBinding:
    capability = _capability(
        _NativeCapabilityFields(
            definition.metadata.id,
            description.operation_name,
            description.label,
            description.description,
            _description_input_schema(description.parameters),
            _description_output_schema(description),
        )
    ).model_copy(
        update={
            "connector_display_name": definition.metadata.display_name,
            "connector_capability_description": definition.metadata.capability_description,
        }
    )
    return NativeCapabilityBinding(
        capability,
        None,
        mangle_public_tool_name(definition.tool_name_prefix, description.operation_name),
    )


@dataclass(frozen=True)
class _NativeCapabilityFields:
    connector_id: str
    operation_name: str
    title: str
    description: str
    input_schema: dict[str, object]
    output_schema: AbsentCapabilityOutputSchema | PresentCapabilityOutputSchema
    capability_kind: CapabilityKind = "tool"


def _binding_from_prompt(
    definition: ConnectorDefinition, prompt: ConnectorPromptCatalogDescription
) -> NativeCapabilityBinding:
    capability = _capability(
        _NativeCapabilityFields(
            definition.metadata.id,
            prompt.name,
            prompt.name,
            prompt.description,
            {"properties": {}, "type": "object"},
            AbsentCapabilityOutputSchema(),
            "prompt",
        )
    ).model_copy(
        update={
            "connector_display_name": definition.metadata.display_name,
            "connector_capability_description": definition.metadata.capability_description,
        }
    )
    return NativeCapabilityBinding(capability, None, "")


def _binding_from_resource(
    definition: ConnectorDefinition, resource: ConnectorResourceCatalogDescription
) -> NativeCapabilityBinding:
    capability_kind: CapabilityKind = (
        "resource_template" if resource.kind == "resource_template" else "resource"
    )
    capability = _capability(
        _NativeCapabilityFields(
            definition.metadata.id,
            resource.uri,
            resource.name,
            resource.description,
            {"properties": {}, "type": "object"},
            AbsentCapabilityOutputSchema(),
            capability_kind,
        )
    ).model_copy(
        update={
            "connector_display_name": definition.metadata.display_name,
            "connector_capability_description": definition.metadata.capability_description,
        }
    )
    return NativeCapabilityBinding(capability, None, "")


def _capability(fields: _NativeCapabilityFields) -> NormalizedCapability:
    return NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="native",
            connector_id=fields.connector_id,
            capability_kind=fields.capability_kind,
            capability_key=fields.operation_name,
        ),
        title=fields.title,
        description=fields.description,
        input_schema=fields.input_schema,
        output_schema=fields.output_schema,
    )


def _mapping_input_schema(mapping: ConnectorToolMapping) -> dict[str, object]:
    operation_signature = signature(mapping.operation)
    descriptions = _parameter_descriptions(getattr(mapping, "parameters", ()))
    properties = {
        name: TypeAdapter(_annotation(parameter.annotation, descriptions.get(name, ""))).json_schema()
        for name, parameter in operation_signature.parameters.items()
    }
    required = [
        name
        for name, parameter in operation_signature.parameters.items()
        if parameter.default is Parameter.empty
    ]
    return _object_schema(properties, required)


def _description_input_schema(
    parameters: Sequence[ConnectorToolParameterDescription],
) -> dict[str, object]:
    properties = {
        parameter.name: {"type": parameter.type, "description": parameter.description}
        for parameter in parameters
    }
    required = [parameter.name for parameter in parameters if parameter.required]
    return _object_schema(properties, required)


def _object_schema(
    properties: Mapping[str, object], required: Sequence[str]
) -> dict[str, object]:
    schema: dict[str, object] = {"properties": dict(properties), "type": "object"}
    if required:
        schema["required"] = list(required)
    return schema


def _parameter_descriptions(parameters: object) -> dict[str, str]:
    if isinstance(parameters, Mapping):
        properties = parameters.get("properties", {})
        if not isinstance(properties, Mapping):
            return {}
        return {
            str(name): str(schema["description"])
            for name, schema in properties.items()
            if isinstance(schema, Mapping) and isinstance(schema.get("description"), str)
        }
    return {
        parameter.name: parameter.description
        for parameter in parameters
        if isinstance(parameter, ConnectorToolParameterDescription)
    }


def _annotation(annotation: object, description: str) -> object:
    resolved = Any if annotation is Signature.empty else annotation
    return Annotated[resolved, Field(description=description)] if description else resolved


def _mapping_output_schema(
    mapping: ConnectorToolMapping,
) -> AbsentCapabilityOutputSchema | PresentCapabilityOutputSchema:
    output_schema = getattr(mapping, "output_schema", None)
    if isinstance(output_schema, PresentConnectorToolOutputSchema):
        return PresentCapabilityOutputSchema(schema=output_schema.output_schema)
    return AbsentCapabilityOutputSchema()


def _description_output_schema(
    description: ConnectorToolDescriptionState,
) -> AbsentCapabilityOutputSchema | PresentCapabilityOutputSchema:
    if hasattr(description, "output_schema"):
        return PresentCapabilityOutputSchema(schema=description.output_schema)
    return AbsentCapabilityOutputSchema()


def _duplicate_identity(bindings: Sequence[NativeCapabilityBinding]) -> CapabilityIdentity:
    seen: set[CapabilityIdentity] = set()
    for binding in bindings:
        if binding.capability.identity in seen:
            return binding.capability.identity
        seen.add(binding.capability.identity)
    raise ValueError("Capabilities do not contain duplicate identities")
