from umbod.mcp.connectors.downstream_mcp.ports import DownstreamClientFactory
from umbod.mcp.connectors.downstream_mcp.resource_access import AccessCheckedTemplate

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from contextvars import ContextVar, Token
from functools import partial
from typing import Any
from fastmcp.client import Client
from fastmcp.prompts import Prompt
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.base import Provider
from fastmcp.server.providers.proxy import ProxyPrompt, ProxyResource, ProxyTemplate, ProxyTool
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
from mcp.types import Prompt as McpPrompt, Resource as McpResource, ResourceTemplate as McpResourceTemplate
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
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredTool, uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.runtime import DownstreamRuntimeResolver, DownstreamRuntimeUnavailable, SharedDownstreamRuntimeResolver
from umbod.mcp.connectors.downstream_mcp.permissions import DownstreamToolPermissionPolicy, DownstreamToolPermissionPolicySource
from umbod.mcp.connectors.native.tools import (
    ConnectorTelemetryInterceptor,
    ConnectorToolInvocationIdentity,
    ConnectorToolSearchCandidate,
)
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedDownstreamProxyTool, AuthorizedPersonalTool
from umbod.mcp.connectors.downstream_mcp.tool_projection import tool_descriptor_options
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRuntime, PersonalToolRecord
from umbod.mcp.logging import ConnectorToolInvocationLogger
from umbod.mcp.metrics import InvocationScope, McpMetricsRecorder, ToolInvocationMetricIdentity
from umbod.mcp.tools.invocation.telemetry import initialize_invocation_metrics
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

    async def prepare(self, connector_id: str) -> DiscoverDownstreamTools | None:
        query = ConnectorIdQuery(connector_id=connector_id)
        definition = await self.definitions.get(query)
        if not isinstance(definition, ConnectorDefinitionFound) or uses_personal_oauth(definition.definition):
            return None
        credential = await self.credentials.get(query)
        if not isinstance(credential, CredentialFound):
            return None
        return DiscoverDownstreamTools(definition=definition.definition, credential=credential.credential)

    async def connector_is_eligible(self, connector_id: str) -> bool:
        query = ConnectorIdQuery(connector_id=connector_id)
        return await self.prepare(connector_id) is not None and isinstance(await self.catalogs.get(query), ToolCatalogFound) and await self.publishing.is_published(connector_id)

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

    def __init__(self, policy: DownstreamToolPermissionPolicy) -> None:
        self._policy = policy

    async def allows(self, identity: CapabilityIdentity) -> bool:
        return self._policy.allows_capability(
            identity.connector_id, identity.capability_kind, identity.capability_key
        )

@dataclass(frozen=True)
class _AvailabilityDependencies:
    stores: ConnectorStoreService
    capabilities: StoreBackedDownstreamCapabilityCatalog
    publishing: ConnectorPublishingStore
    activations: ActivationStore
    permissions: DownstreamToolPermissionPolicy

def _availability(dependencies: _AvailabilityDependencies) -> CapabilityAvailability:
    return CapabilityAvailability(ConnectorStoreCapabilityPublication('downstream_mcp', dependencies.publishing), ConnectorStoreCapabilityActivation('downstream_mcp', dependencies.activations), _DownstreamCapabilityReadiness(dependencies.stores, dependencies.capabilities), _DownstreamCapabilityPermissions(dependencies.permissions))

async def _effective_descriptions(store: ConnectorCapabilityDescriptionOverrideStore, records: tuple[DownstreamCapabilityRecord, ...]) -> dict[str, str]:
    definitions = tuple({record.definition.connector_id: record.definition for record in records}.values())
    keys = tuple((ConnectorCapabilityDescriptionKey(kind='downstream_mcp', connector_id=item.connector_id) for item in definitions))
    states = await store.get_many(keys)
    return {item.connector_id: state.description if isinstance(state, OverriddenCapabilityDescription) else item.capability_description for (item, state) in zip(definitions, states, strict=True)}

class DownstreamMcpToolRuntimeProvider(Provider):

    def __init__(self, *, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, publishing: ConnectorPublishingStore, activations: ActivationStore, client_factory: DownstreamClientFactory, permission_policy: DownstreamToolPermissionPolicySource, connector_scope: str, capability_description_overrides: ConnectorCapabilityDescriptionOverrideStore, tool_invocation_logger: ConnectorToolInvocationLogger, metrics_recorder: McpMetricsRecorder, invocation_policy: ConnectorInvocationPolicy, personal_runtime: PersonalToolRuntime) -> None:
        self._stores = ConnectorStoreService(definitions, credentials, catalogs, publishing, activations)
        self._capabilities = StoreBackedDownstreamCapabilityCatalog(definitions, catalogs)
        self._permission_policy = permission_policy
        self._downstream_client_factory = client_factory
        self._connector_scope = connector_scope
        self._capability_description_overrides = capability_description_overrides
        self._tool_invocation_logger = tool_invocation_logger
        self._metrics_recorder = metrics_recorder
        self._invocation_policy = invocation_policy
        self._personal_runtime = personal_runtime
        super().__init__()

    async def initialize_metrics(self) -> None:
        for record in await self._capabilities.list_records():
            if uses_personal_oauth(record.definition) or record.capability.identity.capability_kind != "tool" or record.source_tool is None:
                continue
            connector_id = record.definition.connector_id
            backend_name = record.source_tool.identity.downstream_name
            self._initialize_tool_metrics(connector_id, mangle_public_tool_name(record.definition.tool_name_prefix, backend_name))
            self._initialize_tool_metrics(connector_id, backend_name)

    def _initialize_tool_metrics(self, connector_id: str, public_name: str) -> None:
        initialize_invocation_metrics(self._metrics_recorder, ToolInvocationMetricIdentity(
            scope=InvocationScope.CONNECTOR, connector_name=connector_id, tool_name=public_name,
        ))

    def _operation_availability(self) -> CapabilityAvailability:
        policy = self._permission_policy.capture()
        dependencies = _AvailabilityDependencies(
            self._stores, self._capabilities, self._stores.publishing, self._stores.activations, policy,
        )
        return _availability(dependencies)

    def _operation_runtime(self) -> DownstreamRuntimeResolver:
        return SharedDownstreamRuntimeResolver(
            self._operation_availability(), self._stores.definitions, self._stores.credentials,
        )

    async def _ensure_capability_access(self, identity: CapabilityIdentity) -> None:
        runtime = self._operation_runtime()
        try:
            await runtime.resolve(identity)
        except DownstreamRuntimeUnavailable as error:
            raise ToolError("Downstream capability is not available") from error

    async def _create_capability_client(self, identity: CapabilityIdentity) -> Client:
        runtime = self._operation_runtime()
        try:
            shared = await runtime.resolve(identity)
        except DownstreamRuntimeUnavailable as error:
            raise ToolError("Downstream capability is not available") from error
        return self._downstream_client_factory.create(shared.command)

    def _active_scope(self) -> str:
        return self._connector_scope or _REQUEST_CONNECTOR_SCOPE.get()

    def _materialize_tool(self, connector_id: str, tool_name_prefix: str, catalog_tool: DiscoveredTool, connector_name: str) -> Tool:
        identity = CapabilityIdentity(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="tool", capability_key=catalog_tool.identity.downstream_name)
        client_factory = partial(self._create_capability_client, identity)
        backend_tool = ProxyTool(client_factory=client_factory, name=catalog_tool.identity.downstream_name, **tool_descriptor_options(catalog_tool))
        public_name = self._public_tool_name(connector_id, tool_name_prefix, backend_tool.name)
        self._initialize_tool_metrics(connector_id, public_name)
        return AuthorizedDownstreamProxyTool(identity=self._invocation_identity(connector_id, connector_name, catalog_tool, public_name), backend_tool=backend_tool, client_factory=client_factory, public_name=public_name, invocation_policy=self._invocation_policy, telemetry_interceptor=self._telemetry_interceptor(connector_name))

    def _materialize_personal_tool(self, record: PersonalToolRecord) -> AuthorizedPersonalTool:
        definition = record.definition
        catalog = record.tool
        public_name = self._public_tool_name(definition.connector_id, definition.tool_name_prefix, catalog.identity.downstream_name)
        options = tool_descriptor_options(catalog)
        return AuthorizedPersonalTool(identity=self._invocation_identity(definition.connector_id, definition.display_name, catalog, public_name), record=record, runtime=self._personal_runtime, public_name=public_name, invocation_policy=self._invocation_policy, telemetry_interceptor=self._telemetry_interceptor(definition.display_name), options=options)

    @staticmethod
    def _invocation_identity(connector_id: str, connector_name: str, catalog_tool: DiscoveredTool, public_name: str) -> ConnectorToolInvocationIdentity:
        return ConnectorToolInvocationIdentity(tool_name=public_name, connector_id=connector_id, connector_name=connector_name, operation_name=catalog_tool.identity.downstream_name)

    def _telemetry_interceptor(self, connector_name: str) -> ConnectorTelemetryInterceptor:
        return ConnectorTelemetryInterceptor(connector_name=connector_name, tool_invocation_logger=self._tool_invocation_logger, metrics_recorder=self._metrics_recorder, result_is_error=lambda result: isinstance(result, ToolResult) and result.is_error)

    def _public_tool_name(self, connector_id: str, tool_name_prefix: str, backend_name: str) -> str:
        if self._active_scope() == connector_id:
            return backend_name
        return mangle_public_tool_name(tool_name_prefix, backend_name)

    async def _configured_tool_records(self) -> tuple[DownstreamCapabilityRecord, ...]:
        scope = self._active_scope()
        scoped = tuple(record for record in await self._capabilities.list_records() if not uses_personal_oauth(record.definition) and record.source_tool is not None and record.capability.identity.capability_kind == "tool" and (not scope or record.definition.connector_id == scope))
        shared_ids = {record.definition.connector_id for record in scoped}
        published = {connector_id for connector_id in shared_ids if await self._stores.publishing.is_published(connector_id)}
        records = tuple(record for record in scoped if record.definition.connector_id in published)
        for record in records:
            name = self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key)
            if await self.is_personal_tool_name(name):
                raise ToolError("public_tool_name_conflict")
        _validate_public_identities([_public_identity(record) for record in records])
        names = tuple(self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key) for record in records)
        if len(set(names)) != len(names):
            raise ToolError("public_tool_name_conflict")
        return records

    async def configured_tool_name_claims(self) -> tuple[str, ...]:
        return tuple(self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key) for record in await self._configured_tool_records())

    async def is_personal_tool_name(self, name: str) -> bool:
        scope = self._active_scope()
        owners: list[str] = []
        sentinel = "UmbodPersonalNamespaceSentinel"
        for definition in (await self._stores.definitions.list()).definitions:
            if not uses_personal_oauth(definition) or (scope and definition.connector_id != scope):
                continue
            stem = mangle_public_tool_name(definition.tool_name_prefix, sentinel).removesuffix(sentinel)
            if not stem:
                raise ToolError("public_tool_name_conflict")
            if scope == definition.connector_id or name == stem.rstrip("_") or name.startswith(stem):
                owners.append(definition.connector_id)
        if len(owners) > 1:
            raise ToolError("public_tool_name_conflict")
        return bool(owners)

    async def owns_tool(self, tool_name: str) -> bool:
        await self._configured_tool_records()
        if await self.is_personal_tool_name(tool_name):
            return True
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
        availability = self._operation_availability()
        await self._configured_tool_records()
        tools: list[Tool] = []
        identities: list[PublicToolIdentity] = []
        active_scope = self._active_scope()
        for record in await self._capabilities.list_records():
            identity = record.capability.identity
            if uses_personal_oauth(record.definition) or identity.capability_kind != "tool" or record.source_tool is None:
                continue
            if active_scope and identity.connector_id != active_scope:
                continue
            if not await availability.is_available(identity):
                continue
            identities.append(_public_identity(record))
            definition = record.definition
            tools.append(self._materialize_tool(definition.connector_id, definition.tool_name_prefix, record.source_tool, definition.display_name))
        for record in await self._personal_runtime.list_tools():
            definition = record.definition
            if active_scope and definition.connector_id != active_scope:
                continue
            identities.append(PublicToolIdentity(connector_id=definition.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=record.tool.identity.downstream_name))
            await self.is_personal_tool_name(self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name))
            tools.append(self._materialize_personal_tool(record))
        _validate_public_identities(identities)
        if len({tool.name for tool in tools}) != len(tools):
            raise ToolError("public_tool_name_conflict")
        return tools

    async def eligible_search_candidates(self) -> list[ConnectorToolSearchCandidate]:
        availability = self._operation_availability()
        await self._configured_tool_records()
        eligible: list[DownstreamCapabilityRecord] = []
        active_scope = self._active_scope()
        for record in await self._capabilities.list_records():
            if active_scope and record.definition.connector_id != active_scope:
                continue
            if uses_personal_oauth(record.definition) or record.capability.identity.capability_kind != "tool":
                continue
            if await availability.is_available(record.capability.identity):
                eligible.append(record)
        records = tuple(eligible)
        descriptions = await _effective_descriptions(self._capability_description_overrides, records)
        identities = [_public_identity(record) for record in records]
        _validate_public_identities(identities)
        candidates = [_search_candidate(record, descriptions[record.definition.connector_id]).model_copy(update={"tool_name": self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key)}) for record in records]
        for record in await self._personal_runtime.list_tools():
            definition = record.definition
            if active_scope and definition.connector_id != active_scope:
                continue
            identities.append(PublicToolIdentity(connector_id=definition.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=record.tool.identity.downstream_name))
            await self.is_personal_tool_name(self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name))
            candidates.append(ConnectorToolSearchCandidate(tool_name=self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name), description=record.tool.description, connector_id=definition.connector_id, connector_display_name=definition.display_name, connector_capability_description=definition.capability_description, operation_name=record.tool.identity.downstream_name, input_schema=record.tool.input_schema, search_hints=(record.tool.title,)))
        _validate_public_identities(identities)
        return candidates

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolResult:
        tools = await self._list_tools()
        matches = tuple(tool for tool in tools if tool.name == tool_name)
        if len(matches) != 1:
            raise ToolError("Unknown tool or tool not available")
        return await matches[0].run(dict(arguments))

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
        backend = ProxyPrompt.from_mcp_prompt(partial(self._create_capability_client, CapabilityIdentity(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="prompt", capability_key=prompt.name)), raw_prompt)
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
        return ProxyResource.from_mcp_resource(partial(self._create_capability_client, CapabilityIdentity(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="resource", capability_key=resource.uri)), raw_resource)

    def _materialize_template(self, connector_id: str, template: DiscoveredResourceTemplate) -> ResourceTemplate:
        meta = {
            **(template.meta or {}),
            "connector_id": connector_id,
            "capability_kind": "resource_template",
            "capability_key": template.uri_template,
            "operation_name": template.uri_template,
        }
        raw_template = McpResourceTemplate(name=template.name, title=template.title, uriTemplate=template.uri_template, description=template.description, mimeType=template.mime_type or None, icons=list(template.icons), annotations=template.annotations or None, _meta=meta)
        identity = CapabilityIdentity(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="resource_template", capability_key=template.uri_template)
        backend = ProxyTemplate.from_mcp_template(partial(self._create_capability_client, identity), raw_template)
        return AccessCheckedTemplate(backend, partial(self._ensure_capability_access, identity))

    async def _list_resources(self) -> Sequence[Resource]:
        availability = self._operation_availability()
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        resources: list[Resource] = []
        for entry in index.resources:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="resource",
                capability_key=entry.capability.uri,
            )
            if await availability.is_available(identity):
                resources.append(self._materialize_resource(entry.connector_id, entry.capability))
        return resources

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        availability = self._operation_availability()
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        templates: list[ResourceTemplate] = []
        for entry in index.resource_templates:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="resource_template",
                capability_key=entry.capability.uri_template,
            )
            if await availability.is_available(identity):
                templates.append(self._materialize_template(entry.connector_id, entry.capability))
        return templates

    async def _list_prompts(self) -> Sequence[Prompt]:
        availability = self._operation_availability()
        index = DownstreamCapabilityIndex(await self._eligible_catalogs())
        prompts: list[Prompt] = []
        for entry in index.prompts:
            identity = CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=entry.connector_id,
                capability_kind="prompt",
                capability_key=entry.capability.name,
            )
            if await availability.is_available(identity):
                prompts.append(self._materialize_prompt(entry.connector_id, entry.capability))
        return prompts

    async def _capability_enabled(
        self, connector_id: str, capability_kind: str, capability_key: str
    ) -> bool:
        availability = self._operation_availability()
        identity = CapabilityIdentity(
            connector_kind="downstream_mcp",
            connector_id=connector_id,
            capability_kind=capability_kind,  # type: ignore[arg-type]
            capability_key=capability_key,
        )
        return await availability.is_available(identity)

    async def native_capability_projection(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
        await self.initialize_metrics()
        catalogs = await self._eligible_catalogs()
        return DownstreamCapabilityIndex(catalogs).native_projection()

    async def is_eligible(self, connector_id: str, operation_name: str) -> bool:
        if self._active_scope() and self._active_scope() != connector_id:
            return False
        return any(candidate.connector_id == connector_id and candidate.operation_name == operation_name for candidate in await self.eligible_search_candidates())
