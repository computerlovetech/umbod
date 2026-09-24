from umbod.mcp.downstream_mcp_connectors.ports import DownstreamClientFactory

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from contextvars import ContextVar, Token
from functools import partial
from typing import Any, Protocol
from fastmcp.client import Client
from fastmcp.server.dependencies import get_access_token
from fastmcp.prompts import Prompt
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.base import Provider
from fastmcp.server.providers.proxy import ProxyPrompt, ProxyProvider, ProxyResource, ProxyTemplate, ProxyTool
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
from mcp.types import Prompt as McpPrompt, Resource as McpResource, ResourceTemplate as McpResourceTemplate, Tool as McpTool
from umbod.core.capabilities import (
    CapabilityAvailability,
    CapabilityIdentity,
    CapabilityNotFoundError,
    CapabilityPermissionPolicy,
    CapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
)
from umbod.core.invocation import ConnectorInvocationPolicy
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionKey, ConnectorCapabilityDescriptionOverrideStore, OverriddenCapabilityDescription
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, mangle_public_tool_name, validate_unique_public_tool_names
from umbod.core.activation import ActivationStore
from umbod.core.connectors.downstream_mcp.catalog import DownstreamCapabilityRecord, StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredTool
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.tools import (
    ConnectorTelemetryInterceptor,
    ConnectorToolInvocationIdentity,
    ConnectorToolSearchCandidate,
)
from umbod.mcp.downstream_mcp_connectors.tool_invocation import AuthorizedDownstreamProxyTool
from umbod.mcp.logging import ConnectorToolInvocationLogger
from umbod.mcp.metrics import McpMetricsRecorder
logger = logging.getLogger(__name__)

def _log_collisions(capability_kind: str, owners: Mapping[str, list[str]]) -> None:
    for identifier in sorted(owners):
        conflicting_owners = sorted(owners[identifier])
        if len(conflicting_owners) > 1:
            logger.warning('Downstream MCP capability collision', extra={'capability_kind': capability_kind, 'identifier': identifier, 'owners': conflicting_owners})
_REQUEST_CONNECTOR_SCOPE: ContextVar[str] = ContextVar('downstream_mcp_connector_scope', default='')

def set_request_connector_scope(connector_id: str) -> Token[str]:
    return _REQUEST_CONNECTOR_SCOPE.set(connector_id)

def reset_request_connector_scope(token: Token[str]) -> None:
    _REQUEST_CONNECTOR_SCOPE.reset(token)

class DownstreamToolPermissionPolicy(Protocol):

    def allows(self, connector_id: str, operation_name: str) -> bool:
        ...

    def allows_capability(
        self, connector_id: str, capability_kind: str, capability_key: str
    ) -> bool:
        ...

class UnrestrictedDownstreamToolPermissionPolicy:

    def allows(self, connector_id: str, operation_name: str) -> bool:
        return True

    def allows_capability(
        self, connector_id: str, capability_kind: str, capability_key: str
    ) -> bool:
        return True

class GroupDownstreamToolPermissionPolicy:

    def __init__(self, permissions: InMemoryGroupConnectorToolPermissions) -> None:
        self._permissions = permissions

    def allows(self, connector_id: str, operation_name: str) -> bool:
        return self.allows_capability(connector_id, "tool", operation_name)

    def allows_capability(
        self, connector_id: str, capability_kind: str, capability_key: str
    ) -> bool:
        token = get_access_token()
        claims = getattr(token, 'claims', {}) if token is not None else {}
        if not isinstance(claims, Mapping):
            return False
        from umbod.core.permissions.runtime import ConnectorCapabilityPermission
        return ConnectorCapabilityPermission(
            connector_id=connector_id,
            capability_kind=capability_kind,  # type: ignore[arg-type]
            capability_key=capability_key,
        ) in self._permissions.allowed_capabilities(claims)

@dataclass(frozen=True)
class IndexedDownstreamPrompt:
    connector_id: str
    capability: DiscoveredPrompt
    public_name: str

@dataclass(frozen=True)
class IndexedDownstreamResource:
    connector_id: str
    capability: DiscoveredResource

@dataclass(frozen=True)
class IndexedDownstreamResourceTemplate:
    connector_id: str
    capability: DiscoveredResourceTemplate

class DownstreamCapabilityIndex:

    def __init__(self, catalogs: Sequence[tuple[str, ToolCatalogFound]]) -> None:
        self._prompts = self._flatten_prompts(catalogs)
        self._resources = self._flatten_resources(catalogs)
        self._templates = self._flatten_templates(catalogs)
        self._prompt_owners = self._owners(((entry.public_name, entry.connector_id) for entry in self._prompts))
        self._resource_owners = self._owners(((entry.capability.uri, entry.connector_id) for entry in self._resources), ((entry.capability.uri_template, entry.connector_id) for entry in self._templates))
        _log_collisions('prompt', self._prompt_owners)
        _log_collisions('resource', self._resource_owners)

    @staticmethod
    def _flatten_prompts(catalogs: Sequence[tuple[str, ToolCatalogFound]]) -> tuple[IndexedDownstreamPrompt, ...]:
        return tuple((IndexedDownstreamPrompt(connector_id=connector_id, capability=prompt, public_name=mangle_public_tool_name(connector_id, prompt.name)) for (connector_id, catalog) in catalogs for prompt in catalog.snapshot.prompts))

    @staticmethod
    def _flatten_resources(catalogs: Sequence[tuple[str, ToolCatalogFound]]) -> tuple[IndexedDownstreamResource, ...]:
        return tuple((IndexedDownstreamResource(connector_id=connector_id, capability=resource) for (connector_id, catalog) in catalogs for resource in catalog.snapshot.resources))

    @staticmethod
    def _flatten_templates(catalogs: Sequence[tuple[str, ToolCatalogFound]]) -> tuple[IndexedDownstreamResourceTemplate, ...]:
        return tuple((IndexedDownstreamResourceTemplate(connector_id=connector_id, capability=template) for (connector_id, catalog) in catalogs for template in catalog.snapshot.resource_templates))

    @staticmethod
    def _owners(*entries: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = {}
        for group in entries:
            for (identifier, connector_id) in group:
                owners.setdefault(identifier, []).append(connector_id)
        return owners

    @property
    def prompts(self) -> tuple[IndexedDownstreamPrompt, ...]:
        return tuple((entry for entry in self._prompts if len(self._prompt_owners[entry.public_name]) == 1))

    @property
    def resources(self) -> tuple[IndexedDownstreamResource, ...]:
        return tuple((entry for entry in self._resources if len(self._resource_owners[entry.capability.uri]) == 1))

    @property
    def resource_templates(self) -> tuple[IndexedDownstreamResourceTemplate, ...]:
        return tuple((entry for entry in self._templates if len(self._resource_owners[entry.capability.uri_template]) == 1))

    def native_projection(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
        prompts = tuple(sorted(((entry.public_name, entry.capability.model_dump(mode='json')) for entry in self.prompts), key=repr))
        projected_resources = [('resource', entry.capability.model_dump(mode='json')) for entry in self.resources]
        projected_templates = [('template', entry.capability.model_dump(mode='json')) for entry in self.resource_templates]
        resources = tuple(sorted(projected_resources + projected_templates, key=repr))
        return (prompts, resources)

class NativeCapabilityProviderView(Provider):

    def __init__(self, provider: 'ConnectorAwareDownstreamMcpToolProvider') -> None:
        self._provider = provider
        super().__init__()

    async def _list_resources(self) -> Sequence[Resource]:
        return await self._provider.list_resources()

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        return await self._provider.list_resource_templates()

    async def _list_prompts(self) -> Sequence[Prompt]:
        return await self._provider.list_prompts()

class ConnectorStoreService:

    def __init__(self, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, publishing: ConnectorPublishingStore, activations: ActivationStore) -> None:
        self.definitions = definitions
        self.credentials = credentials
        self.catalogs = catalogs
        self.publishing = publishing
        self.activations = activations
        self.prepared_connectors: dict[str, DiscoverDownstreamTools] = {}

    async def prepare(self, connector_id: str) -> bool:
        query = ConnectorIdQuery(connector_id=connector_id)
        definition = await self.definitions.get(query)
        credential = await self.credentials.get(query)
        if not isinstance(definition, ConnectorDefinitionFound) or not isinstance(credential, CredentialFound):
            self.prepared_connectors.pop(connector_id, None)
            return False
        self.prepared_connectors[connector_id] = DiscoverDownstreamTools(definition=definition.definition, credential=credential.credential)
        return True

    async def connector_is_eligible(self, connector_id: str) -> bool:
        query = ConnectorIdQuery(connector_id=connector_id)
        return await self.prepare(connector_id) and isinstance(await self.catalogs.get(query), ToolCatalogFound) and await self.publishing.is_published(connector_id)

class _DownstreamCapabilityReadiness(CapabilityReadiness):

    def __init__(self, stores: ConnectorStoreService, capabilities: StoreBackedDownstreamCapabilityCatalog) -> None:
        self._stores = stores
        self._capabilities = capabilities

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        if not await self._stores.prepare(identity.connector_id):
            return False
        try:
            await self._capabilities.resolve(identity)
        except CapabilityNotFoundError:
            return False
        return True

class _DownstreamCapabilityPermissions(CapabilityPermissionPolicy):

    def __init__(self, policy: Callable[[], DownstreamToolPermissionPolicy]) -> None:
        self._policy = policy

    async def allows(self, identity: CapabilityIdentity) -> bool:
        return self._policy().allows_capability(
            identity.connector_id, identity.capability_kind, identity.capability_key
        )

@dataclass(frozen=True)
class _AvailabilityDependencies:
    stores: ConnectorStoreService
    capabilities: StoreBackedDownstreamCapabilityCatalog
    publishing: ConnectorPublishingStore
    activations: ActivationStore
    permissions: Callable[[], DownstreamToolPermissionPolicy]

def _availability(dependencies: _AvailabilityDependencies) -> CapabilityAvailability:
    return CapabilityAvailability(ConnectorStoreCapabilityPublication('downstream_mcp', dependencies.publishing), ConnectorStoreCapabilityActivation('downstream_mcp', dependencies.activations), _DownstreamCapabilityReadiness(dependencies.stores, dependencies.capabilities), _DownstreamCapabilityPermissions(dependencies.permissions))

async def _effective_descriptions(store: ConnectorCapabilityDescriptionOverrideStore, records: tuple[DownstreamCapabilityRecord, ...]) -> dict[str, str]:
    definitions = tuple({record.definition.connector_id: record.definition for record in records}.values())
    keys = tuple((ConnectorCapabilityDescriptionKey(kind='downstream_mcp', connector_id=item.connector_id) for item in definitions))
    states = await store.get_many(keys)
    return {item.connector_id: state.description if isinstance(state, OverriddenCapabilityDescription) else item.capability_description for (item, state) in zip(definitions, states, strict=True)}

class DownstreamMcpToolRuntimeProvider(Provider):

    def __init__(self, *, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, publishing: ConnectorPublishingStore, activations: ActivationStore, client_factory: DownstreamClientFactory, permission_policy: DownstreamToolPermissionPolicy, connector_scope: str, capability_description_overrides: ConnectorCapabilityDescriptionOverrideStore, tool_invocation_logger: ConnectorToolInvocationLogger, metrics_recorder: McpMetricsRecorder, invocation_policy: ConnectorInvocationPolicy) -> None:
        self._stores = ConnectorStoreService(definitions, credentials, catalogs, publishing, activations)
        self._capabilities = StoreBackedDownstreamCapabilityCatalog(definitions, catalogs)
        self._permission_policy = permission_policy
        availability_dependencies = _AvailabilityDependencies(self._stores, self._capabilities, publishing, activations, lambda : self._permission_policy)
        self._availability = _availability(availability_dependencies)
        self._downstream_client_factory = client_factory
        self._connector_scope = connector_scope
        self._capability_description_overrides = capability_description_overrides
        self._tool_invocation_logger = tool_invocation_logger
        self._metrics_recorder = metrics_recorder
        self._invocation_policy = invocation_policy
        self._connector_proxies: dict[str, ProxyProvider] = {}
        super().__init__()

    def _create_client(self, connector_id: str) -> Client:
        command = self._stores.prepared_connectors.get(connector_id)
        if command is None:
            raise ToolError('Downstream connector is not available')
        return self._downstream_client_factory.create(command)

    def _create_authorized_client(self, connector_id: str, operation_name: str) -> Client:
        return self._create_client(connector_id)

    def _create_capability_client(self, connector_id: str) -> Client:
        return self._create_client(connector_id)

    def _proxy_for(self, connector_id: str) -> ProxyProvider:
        proxy = self._connector_proxies.get(connector_id)
        if proxy is None:
            proxy = ProxyProvider(partial(self._create_client, connector_id), cache_ttl=0)
            self._connector_proxies[connector_id] = proxy
        return proxy

    def _active_scope(self) -> str:
        return self._connector_scope or _REQUEST_CONNECTOR_SCOPE.get()

    def _materialize_tool(self, connector_id: str, tool_name_prefix: str, catalog_tool: DiscoveredTool, connector_name: str) -> Tool:
        raw_tool = self._catalog_mcp_tool(catalog_tool)
        proxy = self._proxy_for(connector_id)
        backend_tool = ProxyTool.from_mcp_tool(proxy.client_factory, raw_tool)
        public_name = self._public_tool_name(connector_id, tool_name_prefix, backend_tool.name)
        return AuthorizedDownstreamProxyTool(identity=self._invocation_identity(connector_id, connector_name, catalog_tool, public_name), backend_tool=backend_tool, client_factory=partial(self._create_authorized_client, connector_id, catalog_tool.identity.downstream_name), public_name=public_name, invocation_policy=self._invocation_policy, telemetry_interceptor=self._telemetry_interceptor(connector_name))

    @staticmethod
    def _invocation_identity(connector_id: str, connector_name: str, catalog_tool: DiscoveredTool, public_name: str) -> ConnectorToolInvocationIdentity:
        return ConnectorToolInvocationIdentity(tool_name=public_name, connector_id=connector_id, connector_name=connector_name, operation_name=catalog_tool.identity.downstream_name)

    def _telemetry_interceptor(self, connector_name: str) -> ConnectorTelemetryInterceptor:
        return ConnectorTelemetryInterceptor(connector_name=connector_name, tool_invocation_logger=self._tool_invocation_logger, metrics_recorder=self._metrics_recorder, result_is_error=lambda result: isinstance(result, ToolResult) and result.is_error)

    def _public_tool_name(self, connector_id: str, tool_name_prefix: str, backend_name: str) -> str:
        if self._active_scope() == connector_id:
            return backend_name
        return mangle_public_tool_name(tool_name_prefix, backend_name)

    @staticmethod
    def _catalog_mcp_tool(catalog_tool: DiscoveredTool) -> McpTool:
        return McpTool(name=catalog_tool.identity.downstream_name, title=catalog_tool.title, description=catalog_tool.description, inputSchema=catalog_tool.input_schema, outputSchema=catalog_tool.output_schema if catalog_tool.output_schema_status == 'present' else None, annotations=catalog_tool.annotations or None, icons=list(catalog_tool.icons), _meta=catalog_tool.meta or None, execution=catalog_tool.execution or None)

    async def owns_tool(self, tool_name: str) -> bool:
        return any((candidate.tool_name == tool_name for candidate in await self.eligible_search_candidates()))

def _public_identity(record: DownstreamCapabilityRecord) -> PublicToolIdentity:
    identity = record.capability.identity
    return PublicToolIdentity(connector_id=identity.connector_id, tool_name_prefix=record.definition.tool_name_prefix, operation_name=identity.capability_key)

def _public_tool_name(record: DownstreamCapabilityRecord) -> str:
    return mangle_public_tool_name(record.definition.tool_name_prefix, record.capability.identity.capability_key)

def _validate_public_identities(identities: list[PublicToolIdentity]) -> None:
    try:
        validate_unique_public_tool_names(tuple(identities))
    except PublicToolNameConflictError as error:
        raise ToolError(f'public_tool_name_conflict:{error.public_name}') from error

def _search_candidate(record: DownstreamCapabilityRecord, capability_description: str) -> ConnectorToolSearchCandidate:
    capability = record.capability
    definition = record.definition
    return ConnectorToolSearchCandidate(tool_name=_public_tool_name(record), description=capability.description, connector_id=definition.connector_id, connector_display_name=definition.display_name, connector_capability_description=capability_description, operation_name=capability.identity.capability_key, input_schema=capability.input_schema, search_hints=(capability.title,))

class ConnectorAwareDownstreamMcpToolProvider(DownstreamMcpToolRuntimeProvider):

    async def _list_tools(self) -> Sequence[Tool]:
        tools: list[Tool] = []
        identities: list[PublicToolIdentity] = []
        active_scope = self._active_scope()
        for record in await self._capabilities.list_records():
            identity = record.capability.identity
            if identity.capability_kind != "tool" or record.source_tool is None:
                continue
            if active_scope and identity.connector_id != active_scope:
                continue
            if not await self._availability.is_available(identity):
                continue
            identities.append(_public_identity(record))
            definition = record.definition
            tools.append(self._materialize_tool(definition.connector_id, definition.tool_name_prefix, record.source_tool, definition.display_name))
        if not active_scope:
            _validate_public_identities(identities)
        return tools

    async def eligible_search_candidates(self) -> list[ConnectorToolSearchCandidate]:
        eligible: list[DownstreamCapabilityRecord] = []
        for record in await self._capabilities.list_records():
            if record.capability.identity.capability_kind != "tool":
                continue
            if await self._availability.is_available(record.capability.identity):
                eligible.append(record)
        records = tuple(eligible)
        descriptions = await _effective_descriptions(self._capability_description_overrides, records)
        identities = [_public_identity(record) for record in records]
        _validate_public_identities(identities)
        return [_search_candidate(record, descriptions[record.definition.connector_id]) for record in records]

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolResult:
        matched = next(
            (
                record
                for record in await self._capabilities.list_records()
                if record.capability.identity.capability_kind == "tool"
                and _public_tool_name(record) == tool_name
            ),
            None,
        )
        if matched is None or matched.source_tool is None:
            raise ToolError(f"Unknown tool: '{tool_name}'")
        record = await self._capabilities.resolve_record(matched.capability.identity)
        if not await self._availability.is_available(record.capability.identity):
            raise ToolError('Downstream connector tool is not available')
        definition = record.definition
        tool = self._materialize_tool(definition.connector_id, definition.tool_name_prefix, record.source_tool, definition.display_name)
        return await tool.run(dict(arguments))

    async def _eligible_catalogs(self) -> list[tuple[str, ToolCatalogFound]]:
        catalogs: list[tuple[str, ToolCatalogFound]] = []
        active_scope = self._active_scope()
        for definition in (await self._stores.definitions.list()).definitions:
            connector_id = definition.connector_id
            if active_scope and connector_id != active_scope:
                continue
            catalog = await self._stores.catalogs.get(ConnectorIdQuery(connector_id=connector_id))
            if await self._stores.connector_is_eligible(connector_id) and isinstance(catalog, ToolCatalogFound):
                catalogs.append((connector_id, catalog))
        return catalogs

    def _materialize_prompt(self, connector_id: str, prompt: DiscoveredPrompt) -> Prompt:
        meta = {
            **(prompt.meta or {}),
            "connector_id": connector_id,
            "capability_kind": "prompt",
            "capability_key": prompt.name,
            "operation_name": prompt.name,
        }
        raw_prompt = McpPrompt(name=prompt.name, title=prompt.title, description=prompt.description, arguments=[argument.model_dump(exclude_none=True) for argument in prompt.arguments], icons=list(prompt.icons), _meta=meta)
        backend = ProxyPrompt.from_mcp_prompt(partial(self._create_capability_client, connector_id), raw_prompt)
        backend._backend_name = prompt.name
        backend.name = mangle_public_tool_name(connector_id, prompt.name)
        return backend

    def _materialize_resource(self, connector_id: str, resource: DiscoveredResource) -> Resource:
        meta = {
            **(resource.meta or {}),
            "connector_id": connector_id,
            "capability_kind": "resource",
            "capability_key": resource.uri,
            "operation_name": resource.uri,
        }
        raw_resource = McpResource(name=resource.name, title=resource.title, uri=resource.uri, description=resource.description, mimeType=resource.mime_type or None, size=resource.size or None, icons=list(resource.icons), annotations=resource.annotations or None, _meta=meta)
        return ProxyResource.from_mcp_resource(partial(self._create_capability_client, connector_id), raw_resource)

    def _materialize_template(self, connector_id: str, template: DiscoveredResourceTemplate) -> ResourceTemplate:
        meta = {
            **(template.meta or {}),
            "connector_id": connector_id,
            "capability_kind": "resource_template",
            "capability_key": template.uri_template,
            "operation_name": template.uri_template,
        }
        raw_template = McpResourceTemplate(name=template.name, title=template.title, uriTemplate=template.uri_template, description=template.description, mimeType=template.mime_type or None, icons=list(template.icons), annotations=template.annotations or None, _meta=meta)
        return ProxyTemplate.from_mcp_template(partial(self._create_capability_client, connector_id), raw_template)

    async def _list_resources(self) -> Sequence[Resource]:
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        resources: list[Resource] = []
        for entry in index.resources:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="resource",
                capability_key=entry.capability.uri,
            )
            if await self._availability.is_available(identity):
                resources.append(self._materialize_resource(entry.connector_id, entry.capability))
        return resources

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        templates: list[ResourceTemplate] = []
        for entry in index.resource_templates:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="resource_template",
                capability_key=entry.capability.uri_template,
            )
            if await self._availability.is_available(identity):
                templates.append(self._materialize_template(entry.connector_id, entry.capability))
        return templates

    async def _list_prompts(self) -> Sequence[Prompt]:
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        prompts: list[Prompt] = []
        for entry in index.prompts:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="prompt",
                capability_key=entry.capability.name,
            )
            if await self._availability.is_available(identity):
                prompts.append(self._materialize_prompt(entry.connector_id, entry.capability))
        return prompts

    async def _capability_enabled(
        self, connector_id: str, capability_kind: str, capability_key: str
    ) -> bool:
        identity = CapabilityIdentity(
            connector_kind="downstream_mcp",
            connector_id=connector_id,
            capability_kind=capability_kind,  # type: ignore[arg-type]
            capability_key=capability_key,
        )
        return await self._availability.is_available(identity)

    async def native_capability_projection(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
        catalogs = await self._eligible_catalogs()
        return DownstreamCapabilityIndex(catalogs).native_projection()

    async def is_eligible(self, connector_id: str, operation_name: str) -> bool:
        return await self._availability.is_available(CapabilityIdentity(connector_kind='downstream_mcp', connector_id=connector_id, capability_kind="tool",
            capability_key=operation_name))
