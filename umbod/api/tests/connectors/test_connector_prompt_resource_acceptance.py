from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Annotated, Any, Protocol

import pytest
from pydantic import ConfigDict, Field, SecretStr
from umbod_sdk.connectors.proxies import Model

from umbod.core.connectors.native.runtime import (
    connector_prompt_mappings,
    connector_resource_mappings,
)
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore


@dataclass(frozen=True)
class ConnectorCapabilityParameter:
    name: str
    description: str
    required: bool
    schema: Mapping[str, Any]


@dataclass(frozen=True)
class ConnectorCapabilityValidationError:
    connector_id: str
    capability_name: str
    message: str


@dataclass(frozen=True)
class ConnectorCapabilityValidationResult:
    accepted: bool
    errors: Sequence[ConnectorCapabilityValidationError]


@dataclass(frozen=True)
class ConnectorPromptDescription:
    connector_id: str
    name: str
    description: str
    parameters: Sequence[ConnectorCapabilityParameter]


@dataclass(frozen=True)
class ConnectorPromptRequest:
    connector_id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ConnectorPromptResponse:
    content: Any


class ConnectorPromptAcceptancePort(Protocol):
    def validate_connector_prompts(
        self,
        connector_id: str,
    ) -> ConnectorCapabilityValidationResult: ...

    def list_available_prompts(
        self,
        *,
        configured_connector_ids: Sequence[str],
        published_connector_ids: Sequence[str],
    ) -> Sequence[ConnectorPromptDescription]: ...

    def request_prompt(
        self,
        request: ConnectorPromptRequest,
    ) -> ConnectorPromptResponse: ...


@dataclass(frozen=True)
class ConnectorResourceDescription:
    connector_id: str
    uri_template: str
    name: str
    description: str
    parameters: Sequence[ConnectorCapabilityParameter]


@dataclass(frozen=True)
class ConnectorResourceRequest:
    connector_id: str
    uri: str


@dataclass(frozen=True)
class ConnectorResourceResponse:
    content: Any


class ConnectorResourceAcceptancePort(Protocol):
    def validate_connector_resources(
        self,
        connector_id: str,
    ) -> ConnectorCapabilityValidationResult: ...

    def list_available_resources(
        self,
        *,
        configured_connector_ids: Sequence[str],
        published_connector_ids: Sequence[str],
    ) -> Sequence[ConnectorResourceDescription]: ...

    def read_resource(
        self,
        request: ConnectorResourceRequest,
    ) -> ConnectorResourceResponse: ...


class KnowledgeBaseConfiguration(Model):
    model_config = ConfigDict(extra="forbid")

    workspace_name: str = Field(description="Workspace name shown to Umbod administrators.")
    api_token: SecretStr = Field(description="API token used to connect to Knowledge Base.")


class ConnectorPromptAcceptanceDriver(ConnectorPromptAcceptancePort):
    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    def validate_connector_prompts(
        self,
        connector_id: str,
    ) -> ConnectorCapabilityValidationResult:
        try:
            registration = self._plugin.registration()
            descriptions = registration.get("prompt_descriptions", [])
            errors = [
                ConnectorCapabilityValidationError(
                    connector_id=connector_id,
                    capability_name=str(description.get("name", "")),
                    message="Prompt declaration is missing required metadata.",
                )
                for description in descriptions
                if not description.get("name") or not description.get("description")
            ]
            return ConnectorCapabilityValidationResult(accepted=not errors, errors=errors)
        except Exception as exc:
            return ConnectorCapabilityValidationResult(
                accepted=False,
                errors=[
                    ConnectorCapabilityValidationError(
                        connector_id=connector_id,
                        capability_name=connector_id,
                        message=str(exc),
                    )
                ],
            )

    def list_available_prompts(
        self,
        *,
        configured_connector_ids: Sequence[str],
        published_connector_ids: Sequence[str],
    ) -> Sequence[ConnectorPromptDescription]:
        registration = self._plugin.registration()
        connector_id = str(registration["id"])
        if (
            connector_id not in configured_connector_ids
            or connector_id not in published_connector_ids
        ):
            return []
        return [
            ConnectorPromptDescription(
                connector_id=connector_id,
                name=str(description["name"]),
                description=str(description["description"]),
                parameters=tuple(
                    ConnectorCapabilityParameter(
                        name=str(parameter.name),
                        description=str(parameter.description),
                        required=bool(parameter.required),
                        schema={},
                    )
                    for parameter in description["parameters"]
                ),
            )
            for description in registration.get("prompt_descriptions", [])
        ]

    async def request_prompt(
        self,
        request: ConnectorPromptRequest,
    ) -> ConnectorPromptResponse:
        mappings = connector_prompt_mappings(
            self._plugin.definition(),
            configuration_store=await _knowledge_base_configuration_store(),
        )
        mapping_by_name = {mapping.name: mapping for mapping in mappings}
        return ConnectorPromptResponse(
            content=await mapping_by_name[request.name].operation(**request.arguments)
        )


class ConnectorResourceAcceptanceDriver(ConnectorResourceAcceptancePort):
    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    def validate_connector_resources(
        self,
        connector_id: str,
    ) -> ConnectorCapabilityValidationResult:
        try:
            registration = self._plugin.registration()
            descriptions = registration.get("resource_descriptions", [])
            errors = [
                ConnectorCapabilityValidationError(
                    connector_id=connector_id,
                    capability_name=str(description.get("uri_template", "")),
                    message="Resource declaration is missing required metadata.",
                )
                for description in descriptions
                if not description.get("uri_template")
                or not description.get("name")
                or not description.get("description")
            ]
            return ConnectorCapabilityValidationResult(accepted=not errors, errors=errors)
        except Exception as exc:
            return ConnectorCapabilityValidationResult(
                accepted=False,
                errors=[
                    ConnectorCapabilityValidationError(
                        connector_id=connector_id,
                        capability_name=connector_id,
                        message=str(exc),
                    )
                ],
            )

    def list_available_resources(
        self,
        *,
        configured_connector_ids: Sequence[str],
        published_connector_ids: Sequence[str],
    ) -> Sequence[ConnectorResourceDescription]:
        registration = self._plugin.registration()
        connector_id = str(registration["id"])
        if (
            connector_id not in configured_connector_ids
            or connector_id not in published_connector_ids
        ):
            return []
        return [
            ConnectorResourceDescription(
                connector_id=connector_id,
                uri_template=str(description["uri_template"]),
                name=str(description["name"]),
                description=str(description["description"]),
                parameters=(),
            )
            for description in registration.get("resource_descriptions", [])
        ]

    async def read_resource(
        self,
        request: ConnectorResourceRequest,
    ) -> ConnectorResourceResponse:
        mappings = connector_resource_mappings(
            self._plugin.definition(),
            configuration_store=await _knowledge_base_configuration_store(),
        )
        for mapping in mappings:
            if mapping.matches(request.uri):
                return ConnectorResourceResponse(content=await mapping.read(request.uri))
        raise LookupError(request.uri)


def test_decorated_connector_method_becomes_available_prompt_after_configuration_and_publication() -> (
    None
):
    plugin = _knowledge_base_connector()
    prompt_driver = ConnectorPromptAcceptanceDriver(plugin)

    prompts = prompt_driver.list_available_prompts(
        configured_connector_ids=["knowledge_base"],
        published_connector_ids=["knowledge_base"],
    )

    assert prompts == [
        ConnectorPromptDescription(
            connector_id="knowledge_base",
            name="summarize_article",
            description="Create a summary prompt for a knowledge base article.",
            parameters=(
                ConnectorCapabilityParameter(
                    name="article_id",
                    description="Knowledge base article ID to summarize.",
                    required=True,
                    schema={},
                ),
            ),
        )
    ]


def test_decorated_connector_method_becomes_available_resource_after_configuration_and_publication() -> (
    None
):
    plugin = _knowledge_base_connector()
    resource_driver = ConnectorResourceAcceptanceDriver(plugin)

    resources = resource_driver.list_available_resources(
        configured_connector_ids=["knowledge_base"],
        published_connector_ids=["knowledge_base"],
    )

    assert resources == [
        ConnectorResourceDescription(
            connector_id="knowledge_base",
            uri_template="kb://articles/{article_id}",
            name="article",
            description="Read a knowledge base article.",
            parameters=(),
        )
    ]


def test_prompts_and_resources_are_hidden_when_connector_is_not_published() -> None:
    plugin = _knowledge_base_connector()
    prompt_driver = ConnectorPromptAcceptanceDriver(plugin)
    resource_driver = ConnectorResourceAcceptanceDriver(plugin)

    prompts = prompt_driver.list_available_prompts(
        configured_connector_ids=["knowledge_base"],
        published_connector_ids=[],
    )
    resources = resource_driver.list_available_resources(
        configured_connector_ids=["knowledge_base"],
        published_connector_ids=[],
    )

    assert prompts == []
    assert resources == []


def test_prompts_and_resources_are_hidden_when_connector_has_no_valid_configuration() -> None:
    plugin = _knowledge_base_connector()
    prompt_driver = ConnectorPromptAcceptanceDriver(plugin)
    resource_driver = ConnectorResourceAcceptanceDriver(plugin)

    prompts = prompt_driver.list_available_prompts(
        configured_connector_ids=[],
        published_connector_ids=["knowledge_base"],
    )
    resources = resource_driver.list_available_resources(
        configured_connector_ids=[],
        published_connector_ids=["knowledge_base"],
    )

    assert prompts == []
    assert resources == []


@pytest.mark.asyncio
async def test_prompt_request_executes_connector_prompt_method() -> None:
    plugin = _knowledge_base_connector()
    prompt_driver = ConnectorPromptAcceptanceDriver(plugin)

    response = await prompt_driver.request_prompt(
        ConnectorPromptRequest(
            connector_id="knowledge_base",
            name="summarize_article",
            arguments={"article_id": "A-1"},
        )
    )

    assert response.content == "Summarize article A-1 from Acme."


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["complete", "explicit_prompt_parameter_metadata"])
async def test_prompt_mapping_exposes_public_parameter_schema(variant: str) -> None:
    plugin = _knowledge_base_connector(variant=variant)

    mappings = connector_prompt_mappings(
        plugin.definition(), configuration_store=await _knowledge_base_configuration_store()
    )

    assert mappings[0].parameters == {
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Knowledge base article ID to summarize.",
            },
        },
        "required": ["article_id"],
    }


@pytest.mark.asyncio
async def test_missing_public_prompt_parameter_description_raises_value_error() -> None:
    plugin = _knowledge_base_connector(variant="missing_prompt_parameter_description")
    configuration_store = await _knowledge_base_configuration_store()

    with pytest.raises(ValueError, match="article_id"):
        connector_prompt_mappings(plugin.definition(), configuration_store=configuration_store)


@pytest.mark.asyncio
async def test_resource_read_executes_connector_resource_method() -> None:
    plugin = _knowledge_base_connector()
    resource_driver = ConnectorResourceAcceptanceDriver(plugin)

    response = await resource_driver.read_resource(
        ConnectorResourceRequest(connector_id="knowledge_base", uri="kb://articles/A-1")
    )

    assert response.content == {"article_id": "A-1", "workspace": "Acme", "title": "Launch notes"}


@pytest.mark.asyncio
async def test_resource_mapping_exposes_fastmcp_registration_metadata() -> None:
    plugin = _knowledge_base_connector()

    mappings = connector_resource_mappings(
        plugin.definition(), configuration_store=await _knowledge_base_configuration_store()
    )

    assert mappings[0].name == "article"
    assert mappings[0].description == "Read a knowledge base article."
    assert mappings[0].parameters == {
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Knowledge base article ID to read.",
            },
        },
        "required": ["article_id"],
    }


@pytest.mark.parametrize(
    "plugin,expected_fragment",
    [
        (lambda: _knowledge_base_connector(variant="invalid_resource_uri"), "uri"),
        (lambda: _knowledge_base_connector(variant="missing_resource_metadata"), "metadata"),
    ],
)
def test_invalid_resource_declarations_are_rejected(plugin: Any, expected_fragment: str) -> None:
    resource_driver = ConnectorResourceAcceptanceDriver(plugin())

    result = resource_driver.validate_connector_resources("knowledge_base")

    assert result.accepted is False
    assert expected_fragment in result.errors[0].message.lower()


@pytest.mark.parametrize(
    "variant,expected_fragment",
    [
        ("missing_prompt_metadata", "metadata"),
        ("missing_prompt_parameter_description", "article_id"),
    ],
)
def test_invalid_prompt_declaration_is_rejected(variant: str, expected_fragment: str) -> None:
    prompt_driver = ConnectorPromptAcceptanceDriver(_knowledge_base_connector(variant=variant))

    result = prompt_driver.validate_connector_prompts("knowledge_base")

    assert result.accepted is False
    assert expected_fragment in result.errors[0].message.lower()


async def _knowledge_base_configuration_store() -> InMemoryConnectorCurrentConfigurationStore:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    await configuration_store.save_current_configuration(
        "knowledge_base",
        KnowledgeBaseConfiguration(workspace_name="Acme", api_token=SecretStr("kb-valid")),
    )
    return configuration_store


def _knowledge_base_connector(variant: str = "complete") -> Any:
    plugin_api = import_module("umbod_sdk.connectors.plugin_api")
    connector = plugin_api.Connector(
        id="knowledge_base",
        name="Knowledge Base",
        description="Knowledge Base connector for acceptance tests.",
        capability_description="Search and read knowledge base articles.",
        configuration=KnowledgeBaseConfiguration,
        extension={"source": "acceptance-test"},
    )

    @connector.configuration_check
    def check_configuration(configuration: KnowledgeBaseConfiguration) -> bool:
        return configuration.api_token.get_secret_value() == "kb-valid"

    _register_knowledge_base_prompt(connector, variant)
    _register_knowledge_base_resource(connector, variant)

    return connector


def _register_knowledge_base_prompt(connector: Any, variant: str) -> None:
    prompt_options: Mapping[str, str] = (
        {}
        if variant == "missing_prompt_metadata"
        else {"description": "Create a summary prompt for a knowledge base article."}
    )
    if variant == "missing_prompt_parameter_description":

        @connector.prompt(**prompt_options)
        def summarize_article(article_id: str, configuration: KnowledgeBaseConfiguration) -> str:
            return f"Summarize article {article_id} from {configuration.workspace_name}."

        return
    if variant == "explicit_prompt_parameter_metadata":

        @connector.prompt(
            parameters={"article_id": "Knowledge base article ID to summarize."}, **prompt_options
        )
        def summarize_article(article_id: str, configuration: KnowledgeBaseConfiguration) -> str:
            return f"Summarize article {article_id} from {configuration.workspace_name}."

        return

    @connector.prompt(**prompt_options)
    def summarize_article(
        article_id: Annotated[str, Field(description="Knowledge base article ID to summarize.")],
        configuration: KnowledgeBaseConfiguration,
    ) -> str:
        return f"Summarize article {article_id} from {configuration.workspace_name}."


def _register_knowledge_base_resource(connector: Any, variant: str) -> None:
    resource_uri = (
        "articles/{article_id}"
        if variant == "invalid_resource_uri"
        else "kb://articles/{article_id}"
    )
    resource_options: Mapping[str, str] = (
        {}
        if variant == "missing_resource_metadata"
        else {"name": "article", "description": "Read a knowledge base article."}
    )

    @connector.resource(resource_uri, **resource_options)
    def read_article(
        article_id: Annotated[str, Field(description="Knowledge base article ID to read.")],
        configuration: KnowledgeBaseConfiguration,
    ) -> Mapping[str, str]:
        return {
            "article_id": article_id,
            "workspace": configuration.workspace_name,
            "title": "Launch notes",
        }
