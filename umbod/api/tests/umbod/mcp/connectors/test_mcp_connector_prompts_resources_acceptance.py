from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any
import pytest
from fastmcp import Client, FastMCP
from pydantic import ConfigDict, Field, SecretStr
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.proxies import Model
from tests.mcp_fixtures import build_test_mcp

class KnowledgeBaseConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    workspace_name: str
    api_token: SecretStr
KNOWLEDGE_BASE_REGISTRATION: dict[str, Any] = {'id': 'knowledge_base', 'display_name': 'Knowledge Base', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to the company knowledge base', 'configuration_schema': KnowledgeBaseConfiguration}
SUPPORT_DOCS_REGISTRATION: dict[str, Any] = {'id': 'support_docs', 'display_name': 'Support Docs', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to support documentation', 'configuration_schema': KnowledgeBaseConfiguration}
ARTICLE_PARAMETERS_SCHEMA: dict[str, Any] = {'properties': {'article_id': {'description': 'Knowledge base article ID.', 'type': 'string'}}, 'required': ['article_id'], 'type': 'object'}
DEFAULT_FIELD_PARAMETERS_SCHEMA: dict[str, Any] = {'properties': {'article_id': {'description': 'Default field article ID.', 'type': 'string'}}, 'required': ['article_id'], 'type': 'object'}
RESOURCE_PARAMETERS_SCHEMA: dict[str, Any] = {'properties': {'article_id': {'description': 'Knowledge base article ID.', 'type': 'string'}}, 'required': ['article_id'], 'type': 'object'}

@dataclass(frozen=True)
class PromptMapping:
    connector_id: str
    name: str
    operation: Callable[..., str]
    description: str = 'Create a summary prompt for a knowledge base article.'
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ResourceMapping:
    connector_id: str
    uri_template: str
    read_operation: Callable[..., str]
    name: str = 'knowledge_base_article'
    description: str = 'Read a knowledge base article.'
    parameters: dict[str, Any] = field(default_factory=dict)

    def matches(self, uri: str) -> bool:
        template_parts = self.uri_template.split('/')
        uri_parts = uri.split('/')
        return len(template_parts) == len(uri_parts) and all((template_part.startswith('{') and template_part.endswith('}') or template_part == uri_part for (template_part, uri_part) in zip(template_parts, uri_parts, strict=True)))

    def read(self, uri: str) -> str:
        return self.read_operation(**_uri_arguments(self.uri_template, uri))

@dataclass(frozen=True)
class RuntimeOptions:
    connector_registrations: list[dict[str, Any]] | None = None
    prompt_mappings: list[PromptMapping] | None = None
    resource_mappings: list[ResourceMapping] | None = None

@pytest.mark.asyncio
async def test_published_configured_connector_prompt_is_listed_with_connector_prefix() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    prompt_names = [prompt.name for prompt in prompts]
    assert 'knowledge_base_summarize_article' in prompt_names
    assert 'summarize_article' not in prompt_names

@pytest.mark.asyncio
async def test_published_configured_connector_prompt_can_be_requested() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompt = await client.get_prompt('knowledge_base_summarize_article', {'article_id': 'a-123'})
    assert prompt.messages[0].content.text == 'Summarize article a-123'

@pytest.mark.parametrize('mapping_factory_name', ['annotated', 'metadata'])
@pytest.mark.asyncio
async def test_published_configured_connector_prompt_exposes_description_and_arguments(mapping_factory_name: str) -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article', annotated=mapping_factory_name == 'annotated')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    prompt = next((prompt for prompt in prompts if prompt.name == 'knowledge_base_summarize_article'))
    assert prompt.description == 'Create a summary prompt for a knowledge base article.'
    assert prompt.arguments is not None
    assert prompt.arguments[0].name == 'article_id'
    assert 'Knowledge base article ID.' in str(prompt.arguments[0].description)

@pytest.mark.asyncio
async def test_published_configured_connector_prompt_exposes_default_field_argument_description() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_default_field_prompt_mapping('knowledge_base', 'summarize_article')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    prompt = next((prompt for prompt in prompts if prompt.name == 'knowledge_base_summarize_article'))
    assert prompt.arguments is not None
    assert prompt.arguments[0].name == 'article_id'
    assert 'Default field article ID.' in str(prompt.arguments[0].description)

@pytest.mark.asyncio
async def test_published_configured_connector_resource_template_exposes_metadata() -> None:
    runtime = _runtime(RuntimeOptions(resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    template = next((template for template in templates if template.uri_template == 'kb://articles/{article_id}'))
    assert template.name == 'knowledge_base_article'
    assert template.description == 'Read a knowledge base article.'
    assert template.meta is not None
    assert template.meta['connector'] == {'parameters': RESOURCE_PARAMETERS_SCHEMA}

@pytest.mark.asyncio
async def test_published_configured_connector_resource_can_be_read() -> None:
    runtime = _runtime(RuntimeOptions(resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        resources = await client.read_resource('kb://articles/a-123')
    assert resources[0].text == 'Article a-123'

@pytest.mark.asyncio
async def test_same_declared_prompt_name_from_multiple_connectors_is_exposed_with_unique_prefixes() -> None:
    runtime = _runtime(RuntimeOptions(connector_registrations=[KNOWLEDGE_BASE_REGISTRATION, SUPPORT_DOCS_REGISTRATION], prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize'), _prompt_mapping('support_docs', 'summarize')]))
    await _configure(runtime, 'knowledge_base')
    await _configure(runtime, 'support_docs')
    await _publish(runtime, 'knowledge_base')
    await _publish(runtime, 'support_docs')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    prompt_names = [prompt.name for prompt in prompts]
    assert 'knowledge_base_summarize' in prompt_names
    assert 'support_docs_summarize' in prompt_names
    assert 'summarize' not in prompt_names

@pytest.mark.asyncio
async def test_unpublished_connector_prompts_and_resources_are_hidden() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        templates = await client.list_resource_templates()
    assert 'knowledge_base_summarize_article' not in [prompt.name for prompt in prompts]
    assert 'kb://articles/{article_id}' not in [template.uri_template for template in templates]

@pytest.mark.asyncio
async def test_unconfigured_connector_prompts_and_resources_are_hidden() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        templates = await client.list_resource_templates()
    assert 'knowledge_base_summarize_article' not in [prompt.name for prompt in prompts]
    assert 'kb://articles/{article_id}' not in [template.uri_template for template in templates]

@pytest.mark.asyncio
async def test_connector_prompts_and_resources_do_not_require_tool_activation_or_group_tool_permission() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime, connector_tool_runtime_state_store=None)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        templates = await client.list_resource_templates()
    assert 'knowledge_base_summarize_article' in [prompt.name for prompt in prompts]
    assert 'kb://articles/{article_id}' in [template.uri_template for template in templates]

@pytest.mark.asyncio
async def test_group_tool_permissions_do_not_hide_connector_prompts_and_resources() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    await _publish(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime, connector_tool_runtime_state_store=None)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        templates = await client.list_resource_templates()
    group_permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=('groups',))
    assert isinstance(group_permissions, InMemoryGroupConnectorToolPermissions)
    assert 'knowledge_base_summarize_article' in [prompt.name for prompt in prompts]
    assert 'kb://articles/{article_id}' in [template.uri_template for template in templates]

@pytest.mark.asyncio
async def test_publishing_state_changes_are_reflected_without_rebuilding_mcp_server() -> None:
    runtime = _runtime(RuntimeOptions(prompt_mappings=[_prompt_mapping('knowledge_base', 'summarize_article')], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        prompts_before = await client.list_prompts()
        templates_before = await client.list_resource_templates()
        await _publish(runtime, 'knowledge_base')
        prompts_after_publish = await client.list_prompts()
        templates_after_publish = await client.list_resource_templates()
        assert runtime.connector_publishing_store is not None
        await runtime.connector_publishing_store.unpublish_connector('knowledge_base')
        prompts_after_unpublish = await client.list_prompts()
        templates_after_unpublish = await client.list_resource_templates()
    assert 'knowledge_base_summarize_article' not in [prompt.name for prompt in prompts_before]
    assert 'kb://articles/{article_id}' not in [template.uri_template for template in templates_before]
    assert 'knowledge_base_summarize_article' in [prompt.name for prompt in prompts_after_publish]
    assert 'kb://articles/{article_id}' in [template.uri_template for template in templates_after_publish]
    assert 'knowledge_base_summarize_article' not in [prompt.name for prompt in prompts_after_unpublish]
    assert 'kb://articles/{article_id}' not in [template.uri_template for template in templates_after_unpublish]

@pytest.mark.asyncio
async def test_duplicate_resource_templates_are_not_exposed_for_multiple_connectors() -> None:
    runtime = _runtime(RuntimeOptions(connector_registrations=[KNOWLEDGE_BASE_REGISTRATION, SUPPORT_DOCS_REGISTRATION], resource_mappings=[_resource_mapping('knowledge_base', 'kb://articles/{article_id}'), _resource_mapping('support_docs', 'kb://articles/{article_id}')]))
    await _configure(runtime, 'knowledge_base')
    await _configure(runtime, 'support_docs')
    await _publish(runtime, 'knowledge_base')
    await _publish(runtime, 'support_docs')
    mcp = await build_test_mcp(connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    assert [template.uri_template for template in templates].count('kb://articles/{article_id}') == 1

async def _enable_prompt_and_resource_activations(mcp: FastMCP, runtime: ConnectorRuntime) -> None:
    store = mcp.capability_activation_store
    for mapping in runtime.connector_prompt_mappings:
        await store.set_status(
            CapabilityRef(
                connector_kind="native",
                connector_id=mapping.connector_id,
                capability_kind="prompt",
                capability_key=mapping.name,
            ),
            ActivationStatus.ENABLED,
        )
    for mapping in runtime.connector_resource_mappings:
        await store.set_status(
            CapabilityRef(
                connector_kind="native",
                connector_id=mapping.connector_id,
                capability_kind="resource_template",
                capability_key=mapping.uri_template,
            ),
            ActivationStatus.ENABLED,
        )
    prompt_registry = getattr(mcp, "connector_prompt_registry", None)
    if prompt_registry is not None:
        await prompt_registry.reconcile_all()
    resource_registry = getattr(mcp, "connector_resource_registry", None)
    if resource_registry is not None:
        await resource_registry.reconcile_all()


def _runtime(options: RuntimeOptions) -> ConnectorRuntime:
    resolved_options = options
    return ConnectorRuntime(connector_registrations=resolved_options.connector_registrations or [KNOWLEDGE_BASE_REGISTRATION], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE), connector_tool_mappings=[], connector_prompt_mappings=resolved_options.prompt_mappings or [], connector_resource_mappings=resolved_options.resource_mappings or [])

def _prompt_mapping(connector_id: str, name: str, annotated: bool=True) -> PromptMapping:
    if annotated:

        def operation(article_id: Annotated[str, Field(description='Knowledge base article ID.')]) -> str:
            return f'Summarize article {article_id}'
    else:

        def operation(article_id: str) -> str:
            return f'Summarize article {article_id}'
    return PromptMapping(connector_id=connector_id, name=name, operation=operation, parameters=ARTICLE_PARAMETERS_SCHEMA)

def _default_field_prompt_mapping(connector_id: str, name: str) -> PromptMapping:

    def operation(article_id: str=Field(description='Default field article ID.')) -> str:
        return f'Summarize article {article_id}'
    return PromptMapping(connector_id=connector_id, name=name, operation=operation, parameters=DEFAULT_FIELD_PARAMETERS_SCHEMA)

def _resource_mapping(connector_id: str, uri_template: str) -> ResourceMapping:

    def read_operation(article_id: Annotated[str, Field(description='Knowledge base article ID.')]) -> str:
        return f'Article {article_id}'
    return ResourceMapping(connector_id=connector_id, uri_template=uri_template, read_operation=read_operation, parameters=RESOURCE_PARAMETERS_SCHEMA)

async def _configure(runtime: ConnectorRuntime, connector_id: str) -> None:
    if runtime.connector_configuration_store is None:
        raise RuntimeError('runtime has no configuration store')
    await runtime.connector_configuration_store.save_current_configuration(connector_id, KnowledgeBaseConfiguration(workspace_name='Acme', api_token=SecretStr('kb-valid')))

async def _publish(runtime: ConnectorRuntime, connector_id: str) -> None:
    if runtime.connector_publishing_store is None:
        raise RuntimeError('runtime has no publishing store')
    await runtime.connector_publishing_store.publish_connector(connector_id)

def _uri_arguments(uri_template: str, uri: str) -> dict[str, str]:
    return {template_part[1:-1]: uri_part for (template_part, uri_part) in zip(uri_template.split('/'), uri.split('/'), strict=True) if template_part.startswith('{') and template_part.endswith('}')}
