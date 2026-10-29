from umbod.mcp.connectors.downstream_mcp.personal_discovery import PersonalDiscoveryOperation, PersonalDiscoveryOperations
from umbod.mcp.connectors.downstream_mcp.ports import DownstreamClientFactory
from umbod.mcp.connectors.downstream_mcp.namespaces import PersonalToolNamespaceSnapshot
from umbod.mcp.connectors.downstream_mcp.resource_access import AccessCheckedTemplate

import logging
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from contextvars import ContextVar, Token
from functools import partial
from copy import deepcopy
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
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, mangle_public_tool_name, validate_unique_public_tool_names
from umbod.core.activation import ActivationStore
from umbod.core.connectors.downstream_mcp.catalog import DownstreamCapabilityRecord, StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredTool, uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.runtime import DownstreamRuntimeResolver, DownstreamRuntimeUnavailable, SharedDownstreamRuntimeResolver
from umbod.mcp.connectors.downstream_mcp.permissions import DownstreamToolPermissionPolicy, DownstreamToolPermissionPolicySource
from umbod.mcp.connectors.native.tools import (
    ConnectorToolSearchCandidate,
)
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedDownstreamProxyTool, AuthorizedPersonalTool
from umbod.mcp.connectors.downstream_mcp.tool_projection import tool_descriptor_options
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRuntime, PersonalToolRecord
from umbod.mcp.signals import McpSignals, McpToolExecutionPipelineFactory, McpToolIdentity, ToolInventoryObserved
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoverySnapshot
from umbod.mcp.connectors.downstream_mcp.inventory import shared_tool_inventory
def downstream_result_is_error(result: object) -> bool:
    return isinstance(result, ToolResult) and result.is_error


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

class DownstreamMcpToolRuntimeProvider(Provider):

    def __init__(self, *, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, publishing: ConnectorPublishingStore, activations: ActivationStore, client_factory: DownstreamClientFactory, permission_policy: DownstreamToolPermissionPolicySource, connector_scope: str, signals: McpSignals, execution_pipelines: McpToolExecutionPipelineFactory, personal_runtime: PersonalToolRuntime, personal_discovery: PersonalDiscoveryOperations, discovery_runtime: DownstreamDiscoveryRuntime) -> None:
        self._stores = ConnectorStoreService(definitions, credentials, catalogs, publishing, activations)
        self._capabilities = StoreBackedDownstreamCapabilityCatalog(definitions, catalogs)
        self._permission_policy = permission_policy
        self._downstream_client_factory = client_factory
        self._connector_scope = connector_scope
        self._signals = signals
        self._execution_pipelines = execution_pipelines
        self._personal_runtime = personal_runtime
        self._personal_discovery = personal_discovery
        self._discovery_runtime = discovery_runtime
        super().__init__()

    async def reconcile_runtime(self) -> None:
        await self._discovery_runtime.reconcile()

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

    def discovery_operation(self) -> AbstractAsyncContextManager[PersonalDiscoveryOperation]:
        return self._personal_discovery.operation(self._active_scope())

    def _active_scope(self) -> str:
        return self._connector_scope or _REQUEST_CONNECTOR_SCOPE.get()

    def _materialize_tool(self, connector_id: str, tool_name_prefix: str, catalog_tool: DiscoveredTool, connector_name: str) -> Tool:
        identity = CapabilityIdentity(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="tool", capability_key=catalog_tool.identity.downstream_name)
        client_factory = partial(self._create_capability_client, identity)
        backend_tool = ProxyTool(client_factory=client_factory, name=catalog_tool.identity.downstream_name, **tool_descriptor_options(catalog_tool))
        public_name = self._public_tool_name(connector_id, tool_name_prefix, backend_tool.name)
        self._signals.tool_inventory_observed.send(ToolInventoryObserved((self._invocation_identity(connector_id, connector_name, catalog_tool, public_name),)))
        return AuthorizedDownstreamProxyTool(identity=self._invocation_identity(connector_id, connector_name, catalog_tool, public_name), backend_tool=backend_tool, ensure_access=partial(self._ensure_capability_access, identity), public_name=public_name, execution_pipeline=self._execution_pipelines.create(connector_name, downstream_result_is_error))

    def _materialize_personal_tool(self, record: PersonalToolRecord) -> AuthorizedPersonalTool:
        definition = record.definition
        catalog = record.tool
        public_name = self._public_tool_name(definition.connector_id, definition.tool_name_prefix, catalog.identity.downstream_name)
        options = tool_descriptor_options(catalog)
        return AuthorizedPersonalTool(identity=self._invocation_identity(definition.connector_id, definition.display_name, catalog, public_name), record=record, runtime=self._personal_runtime, discovery=self._personal_discovery, scope=self._active_scope(), public_name=public_name, execution_pipeline=self._execution_pipelines.create(definition.display_name, downstream_result_is_error), options=options)

    @staticmethod
    def _invocation_identity(connector_id: str, connector_name: str, catalog_tool: DiscoveredTool, public_name: str) -> McpToolIdentity:
        return McpToolIdentity(tool_name=public_name, connector_id=connector_id, connector_name=connector_name, operation_name=catalog_tool.identity.downstream_name)

    def _public_tool_name(self, connector_id: str, tool_name_prefix: str, backend_name: str) -> str:
        if self._active_scope() == connector_id:
            return backend_name
        return mangle_public_tool_name(tool_name_prefix, backend_name)

    def _configured_tool_records(self, snapshot: DownstreamDiscoverySnapshot) -> tuple[DownstreamCapabilityRecord, ...]:
        scope = self._active_scope()
        records = tuple(record for record in snapshot.published_records if record.source_tool is not None and record.capability.identity.capability_kind == "tool" and (not scope or record.definition.connector_id == scope))
        namespace = snapshot.namespaces.get(scope, PersonalToolNamespaceSnapshot((), scope))
        for record in records:
            name = self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key)
            if namespace.is_personal_tool_name(name):
                raise ToolError("public_tool_name_conflict")
        _validate_public_identities([_public_identity(record) for record in records])
        names = tuple(self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key) for record in records)
        if len(set(names)) != len(names):
            raise ToolError("public_tool_name_conflict")
        return records

    async def configured_tool_name_claims(self) -> tuple[str, ...]:
        async with self.discovery_operation() as operation:
            return tuple(self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key) for record in self._configured_tool_records(operation.snapshot))

    async def capture_personal_tool_namespace(self) -> PersonalToolNamespaceSnapshot:
        async with self.discovery_operation() as operation:
            namespaces = operation.snapshot.namespaces
            return namespaces.get(self._active_scope(), PersonalToolNamespaceSnapshot((), self._active_scope()))

    async def is_personal_tool_name(self, name: str) -> bool:
        namespace = await self.capture_personal_tool_namespace()
        return namespace.is_personal_tool_name(name)

    async def owns_tool(self, tool_name: str) -> bool:
        async with self.discovery_operation() as operation:
            self._configured_tool_records(operation.snapshot)
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
    return ConnectorToolSearchCandidate(tool_name=_public_tool_name(record), description=capability.description, connector_id=definition.connector_id, connector_display_name=definition.display_name, connector_capability_description=capability_description, operation_name=capability.identity.capability_key, input_schema=deepcopy(capability.input_schema), search_hints=(capability.title,))

class ConnectorAwareDownstreamMcpToolProvider(DownstreamMcpToolRuntimeProvider):

    async def _list_tools(self) -> Sequence[Tool]:
        async with self.discovery_operation() as operation:
            policy = operation.permission_policy
            snapshot = operation.snapshot
            self._configured_tool_records(snapshot)
            tools: list[Tool] = []
            identities: list[PublicToolIdentity] = []
            active_scope = self._active_scope()
            namespace = snapshot.namespaces.get(active_scope, snapshot.namespaces[""])
            personal_records = await operation.records()
            for record in snapshot.available_records:
                identity = record.capability.identity
                if identity.capability_kind != "tool" or record.source_tool is None:
                    continue
                if active_scope and identity.connector_id != active_scope:
                    continue
                if not policy.allows_capability(identity.connector_id, identity.capability_kind, identity.capability_key):
                    continue
                identities.append(_public_identity(record))
                definition = record.definition
                tools.append(self._materialize_tool(definition.connector_id, definition.tool_name_prefix, record.source_tool, definition.display_name))
            for record in personal_records:
                definition = record.definition
                if active_scope and definition.connector_id != active_scope:
                    continue
                identities.append(PublicToolIdentity(connector_id=definition.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=record.tool.identity.downstream_name))
                namespace.is_personal_tool_name(self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name))
                tools.append(self._materialize_personal_tool(record))
            _validate_public_identities(identities)
            if len({tool.name for tool in tools}) != len(tools):
                raise ToolError("public_tool_name_conflict")
            return tools

    async def eligible_search_candidates(self) -> list[ConnectorToolSearchCandidate]:
        async with self.discovery_operation() as operation:
            policy = operation.permission_policy
            snapshot = operation.snapshot
            self._configured_tool_records(snapshot)
            active_scope = self._active_scope()
            namespace = snapshot.namespaces.get(active_scope, snapshot.namespaces[""])
            personal_records = await operation.records()
            records = tuple(record for record in snapshot.available_records if record.capability.identity.capability_kind == "tool" and (not active_scope or record.definition.connector_id == active_scope) and policy.allows_capability(record.definition.connector_id, "tool", record.capability.identity.capability_key))
            identities = [_public_identity(record) for record in records]
            _validate_public_identities(identities)
            candidates = [_search_candidate(record, snapshot.descriptions[record.definition.connector_id]).model_copy(update={"tool_name": self._public_tool_name(record.definition.connector_id, record.definition.tool_name_prefix, record.capability.identity.capability_key)}) for record in records]
            for record in personal_records:
                definition = record.definition
                if active_scope and definition.connector_id != active_scope:
                    continue
                identities.append(PublicToolIdentity(connector_id=definition.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=record.tool.identity.downstream_name))
                namespace.is_personal_tool_name(self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name))
                candidates.append(ConnectorToolSearchCandidate(tool_name=self._public_tool_name(definition.connector_id, definition.tool_name_prefix, record.tool.identity.downstream_name), description=record.tool.description, connector_id=definition.connector_id, connector_display_name=definition.display_name, connector_capability_description=definition.capability_description, operation_name=record.tool.identity.downstream_name, input_schema=deepcopy(record.tool.input_schema), search_hints=(record.tool.title,)))
            _validate_public_identities(identities)
            return candidates

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolResult:
        tools = await self._list_tools()
        matches = tuple(tool for tool in tools if tool.name == tool_name)
        if len(matches) != 1:
            raise ToolError("Unknown tool or tool not available")
        return await matches[0].run(dict(arguments))

    async def _eligible_catalogs(self, snapshot: DownstreamDiscoverySnapshot) -> list[tuple[str, ToolCatalogFound]]:
        active_scope = self._active_scope()
        return [(connector_id, catalog) for connector_id, catalog in snapshot.catalogs if not active_scope or connector_id == active_scope]

    def _materialize_prompt(self, connector_id: str, prompt: DiscoveredPrompt) -> Prompt:
        prompt = prompt.model_copy(deep=True)
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
        resource = resource.model_copy(deep=True)
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
        template = template.model_copy(deep=True)
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
        async with self.discovery_operation() as operation:
            policy = operation.permission_policy
            snapshot = operation.snapshot
            available = frozenset(record.capability.identity for record in snapshot.available_records)
            index = DownstreamCapabilityIndex(await self._eligible_catalogs(snapshot))
            resources: list[Resource] = []
            for entry in index.resources:
                identity = CapabilityIdentity(
                    connector_kind="downstream_mcp",
                    connector_id=entry.connector_id,
                    capability_kind="resource",
                    capability_key=entry.capability.uri,
                )
                if identity in available and policy.allows_capability(identity.connector_id, identity.capability_kind, identity.capability_key):
                    resources.append(self._materialize_resource(entry.connector_id, entry.capability))
            return resources

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        async with self.discovery_operation() as operation:
            policy = operation.permission_policy
            snapshot = operation.snapshot
            available = frozenset(record.capability.identity for record in snapshot.available_records)
            index = DownstreamCapabilityIndex(await self._eligible_catalogs(snapshot))
            templates: list[ResourceTemplate] = []
            for entry in index.resource_templates:
                identity = CapabilityIdentity(
                    connector_kind="downstream_mcp",
                    connector_id=entry.connector_id,
                    capability_kind="resource_template",
                    capability_key=entry.capability.uri_template,
                )
                if identity in available and policy.allows_capability(identity.connector_id, identity.capability_kind, identity.capability_key):
                    templates.append(self._materialize_template(entry.connector_id, entry.capability))
            return templates

    async def _list_prompts(self) -> Sequence[Prompt]:
        async with self.discovery_operation() as operation:
            policy = operation.permission_policy
            snapshot = operation.snapshot
            available = frozenset(record.capability.identity for record in snapshot.available_records)
            index = DownstreamCapabilityIndex(await self._eligible_catalogs(snapshot))
            prompts: list[Prompt] = []
            for entry in index.prompts:
                identity = CapabilityIdentity(
                    connector_kind="downstream_mcp",
                    connector_id=entry.connector_id,
                    capability_kind="prompt",
                    capability_key=entry.capability.name,
                )
                if identity in available and policy.allows_capability(identity.connector_id, identity.capability_kind, identity.capability_key):
                    prompts.append(self._materialize_prompt(entry.connector_id, entry.capability))
            return prompts

    async def native_capability_projection(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
        await self.reconcile_runtime()
        snapshot = self._discovery_runtime.capture()
        self._signals.tool_inventory_observed.send(shared_tool_inventory(snapshot.records))
        catalogs = await self._eligible_catalogs(snapshot)
        return DownstreamCapabilityIndex(catalogs).native_projection()

    async def is_eligible(self, connector_id: str, operation_name: str) -> bool:
        if self._active_scope() and self._active_scope() != connector_id:
            return False
        return any(candidate.connector_id == connector_id and candidate.operation_name == operation_name for candidate in await self.eligible_search_candidates())
