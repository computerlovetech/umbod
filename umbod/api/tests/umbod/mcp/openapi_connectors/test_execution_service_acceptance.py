from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.permissions.stores.schema import CONNECTOR_PERMISSION_TABLE, GROUP_TABLE, CAPABILITY_PERMISSION_TABLE
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.core.persistence import Database
from tests.persistence_runtime import create_inmemory_runtime
import asyncio
from typing import Optional
from pydantic import SecretStr
import pytest
from umbod.core.invocation.tools.execution import create_tool_execution_pipeline
from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationDenied, ConnectorInvocationPolicy, PermitAllConnectorInvocationPolicy
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.execution import AggregateOpenApiOperationResolver, AuthenticatedOutboundRequest, ExactGroupOpenApiCapabilityAuthorizer, MissingJsonBody, OpenApiCapabilityExecutionResult, OpenApiCapabilityExecutionService, OpenApiExecutionLimits, OpenApiExecutionResponse, OpenApiOperationArguments, OpenApiOperationInput, OutboundNetworkError, OutboundPolicyError, OutboundRedirectError, OutboundRequest, OutboundTimeoutError, OutboundTlsError, PresentJsonBody, TrustedBearerAuthorization, UnauthenticatedOpenApiRequestAuthenticator
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore, PersistedOpenApiOperation
from umbod.core.permissions.domain import ConnectorToolRef, SaveGroupPermissionsRequest

async def _grant_connector(permissions: GroupPermissionStoreService, group_id: str, connector_id: str) -> None:
    current = await permissions.list_group_permissions(group_id)
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(group_id=group_id, connector_ids=tuple(sorted((*current.connector_ids, connector_id))), capabilities=current.capabilities))

async def _grant_tool(permissions: GroupPermissionStoreService, group_id: str, tool: ConnectorToolRef) -> None:
    current = await permissions.list_group_permissions(group_id)
    capability = tool.as_capability()
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(group_id=group_id, connector_ids=current.connector_ids, capabilities=tuple(sorted((*current.capabilities, capability), key=lambda candidate: (candidate.connector_id, candidate.capability_kind, candidate.capability_key)))))

class RecordingInvocationPolicy:

    def __init__(self, events: list[str], failure: BaseException | None=None) -> None:
        self.events = events
        self.failure = failure
        self.invocations: list[ConnectorInvocation] = []

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.events.append('policy')
        self.invocations.append(invocation)
        if self.failure is not None:
            raise self.failure

class RecordingCompiler:

    def __init__(self, events: list[str], failure: Exception | None=None) -> None:
        self.events = events
        self.failure = failure
        self.bodies: list[object] = []

    def compile(self, operation: object, arguments: OpenApiOperationArguments, limits: OpenApiExecutionLimits) -> OutboundRequest:
        self.events.append('compile')
        self.bodies.append(arguments.body)
        if self.failure is not None:
            raise self.failure
        return OutboundRequest(method='GET', url='https://approved.example.test/items', headers={}, json_body={}, has_json_body=False, timeout_seconds=limits.timeout_seconds, maximum_response_bytes=limits.maximum_response_bytes, approved_hosts=('approved.example.test',))

class RecordingTransport:

    def __init__(self, events: list[str], failure: BaseException | None=None) -> None:
        self.events = events
        self.failure = failure
        self.requests: list[OutboundRequest] = []

    async def send(self, request: OutboundRequest) -> OpenApiExecutionResponse:
        self.events.append('transport')
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return OpenApiExecutionResponse(status=201, content_type='application/json', headers={'etag': 'x'}, body=b'12345', truncated=True)

class CanaryAuthenticator:

    def __init__(self, canary: str) -> None:
        self._canary = canary

    async def authenticate(self, connector_id: str, request: OutboundRequest) -> AuthenticatedOutboundRequest:
        return AuthenticatedOutboundRequest(**request.model_dump(), authorization=TrustedBearerAuthorization(token=SecretStr(self._canary)))

class RecordingNormalizer:

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def normalize(self, response: OpenApiExecutionResponse) -> OpenApiExecutionResponse:
        self.events.append('normalize')
        return response.model_copy(update={'status': 202, 'body': b'abc'})

class RecordingStore(OpenApiConnectorStoreService):

    def __init__(self, database: Database, events: list[str]) -> None:
        super().__init__(
            database,
            CONNECTOR_TABLE,
                    CURRENT_CATALOG_HEADER_TABLE,
            CATALOG_SOURCE_TABLE,
            CATALOG_OPERATION_TABLE,
            CAPABILITY_ACTIVATION_STATE_TABLE,
        )
        self.events = events

    @classmethod
    async def create(cls, events: list[str]) -> 'RecordingStore':
        base = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
        return cls(base._database, events)

    async def read_operation(self, connector_id: str, operation_id: str) -> Optional[PersistedOpenApiOperation]:
        self.events.append('operation-read')
        return await super().read_operation(connector_id, operation_id)

class RecordingAuthorizer:

    def __init__(self, events: list[str], allowed: bool) -> None:
        self.events = events
        self.allowed = allowed

    async def allows(self, groups: tuple[str, ...], connector_id: str, operation_id: str) -> bool:
        self.events.append('authorize')
        return self.allowed

def _records(catalog_id: str='cat-1', operation_id: str='getItem') -> tuple[OpenApiConnector, OpenApiConnectorCatalog]:
    document: dict[str, object] = {'openapi': '3.1.0', 'info': {'title': 'Inventory', 'version': '1'}, 'servers': [{'url': 'https://approved.example.test'}], 'paths': {'/items': {'get': {'operationId': operation_id, 'responses': {'200': {'description': 'OK'}}}}}}
    candidate = InMemoryOpenApiCandidateImporter().import_candidate(document)
    connector = OpenApiConnector.model_validate({'connector_id': 'inventory', 'display_name': 'Inventory', 'tool_name_prefix': 'Inventory', 'capability_description': 'Inventory capabilities', 'created_at': 'time', 'updated_at': 'time'})
    catalog = OpenApiConnectorCatalog.model_validate({'connector_id': 'inventory', 'catalog_id': catalog_id, 'source_document': document, 'candidate': candidate, 'approved_hosts': ['approved.example.test'], 'selected_server_url': 'https://approved.example.test', 'operation_ids': [operation_id], 'imported_at': 'time'})
    return (connector, catalog)

async def _save(store: OpenApiConnectorStore, records: tuple[OpenApiConnector, OpenApiConnectorCatalog]) -> None:
    (connector, catalog) = records
    await store.save_connector(connector)
    await store.save_catalog(catalog)

def _input(operation_id: str='getItem', body: MissingJsonBody | PresentJsonBody | None=None) -> OpenApiOperationInput:
    return OpenApiOperationInput(connector_id='inventory', operation_id=operation_id, path={}, query={}, headers={}, body=body or MissingJsonBody())

def _service(store: OpenApiConnectorStore, permissions: object, events: list[str], compiler_failure: Exception | None=None, transport_failure: BaseException | None=None, invocation_policy: ConnectorInvocationPolicy=PermitAllConnectorInvocationPolicy()) -> tuple[OpenApiCapabilityExecutionService, RecordingCompiler]:
    compiler = RecordingCompiler(events, compiler_failure)
    return (OpenApiCapabilityExecutionService(store, ExactGroupOpenApiCapabilityAuthorizer(permissions), AggregateOpenApiOperationResolver(), compiler, RecordingTransport(events, transport_failure), RecordingNormalizer(events), OpenApiExecutionLimits(timeout_seconds=1, maximum_response_bytes=5), UnauthenticatedOpenApiRequestAuthenticator(), create_tool_execution_pipeline(invocation_policy, ())), compiler)

def _safe_unavailable() -> OpenApiCapabilityExecutionResult:
    return OpenApiCapabilityExecutionResult(status='error', code='capability_unavailable', message='OpenAPI capability execution failed.')

@pytest.mark.asyncio
async def test_permitted_openapi_invocation_evaluates_sanitized_context_before_one_transport() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events)
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    compiler = RecordingCompiler(events)
    transport = RecordingTransport(events)
    canary = 'authorization-canary-secret'
    service = OpenApiCapabilityExecutionService(store, ExactGroupOpenApiCapabilityAuthorizer(permissions), AggregateOpenApiOperationResolver(), compiler, transport, RecordingNormalizer(events), OpenApiExecutionLimits(timeout_seconds=1, maximum_response_bytes=5), CanaryAuthenticator(canary), create_tool_execution_pipeline(policy, ()))
    result = await service.execute(_input(), ('engineering',))
    assert result.status == 'success'
    assert events == ['compile', 'policy', 'transport', 'normalize']
    assert len(policy.invocations) == 1
    invocation = policy.invocations[0]
    assert invocation.connector_kind == 'openapi'
    assert invocation.connector_id == 'inventory'
    assert invocation.operation_name == 'getItem'
    assert invocation.public_tool_name == 'execute_openapi'
    assert dict(invocation.arguments) == _input().model_dump(mode='python')
    assert canary not in str(dict(invocation.arguments))
    authenticated_request = transport.requests[0]
    assert isinstance(authenticated_request, AuthenticatedOutboundRequest)
    assert authenticated_request.authorization.token.get_secret_value() == canary

@pytest.mark.asyncio
async def test_denied_openapi_invocation_returns_sanitized_failure_without_transport() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, ConnectorInvocationDenied('private rationale'))
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, invocation_policy=policy)
    result = await service.execute(_input(), ('engineering',))
    assert result.code == 'outbound_failed'
    assert 'private rationale' not in result.model_dump_json()
    assert events == ['compile', 'policy']
    assert len(policy.invocations) == 1

@pytest.mark.asyncio
async def test_unexpected_openapi_policy_failure_hides_canary_without_transport() -> None:
    canary = 'policy-canary-secret'
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, RuntimeError(canary))
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, invocation_policy=policy)
    result = await service.execute(_input(), ('engineering',))
    assert result.code == 'outbound_failed'
    assert canary not in result.model_dump_json()
    assert events == ['compile', 'policy']

@pytest.mark.asyncio
async def test_unauthorized_openapi_invocation_skips_policy_and_transport() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events)
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    (service, _) = _service(store, GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE), events, invocation_policy=policy)
    assert await service.execute(_input(), ('engineering',)) == _safe_unavailable()
    assert events == []
    assert policy.invocations == []

@pytest.mark.asyncio
async def test_openapi_policy_cancellation_propagates_without_transport() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, asyncio.CancelledError())
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, invocation_policy=policy)
    with pytest.raises(asyncio.CancelledError):
        await service.execute(_input(), ('engineering',))
    assert events == ['compile', 'policy']

@pytest.mark.asyncio
@pytest.mark.parametrize('grant', ['tool', 'connector'])
async def test_exact_operation_and_connector_grants_authorize(grant: str) -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    if grant == 'tool':
        await _grant_tool(permissions, 'engineering', ConnectorToolRef('inventory', 'getItem'))
    else:
        await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events)
    result = await service.execute(_input(), ('unrelated', 'engineering'))
    assert result.status == 'success'

@pytest.mark.asyncio
@pytest.mark.parametrize('groups,operation_id', [((), 'getItem'), (('wrong',), 'getItem'), (('engineering',), 'other')])
async def test_no_groups_and_wrong_grants_are_indistinguishable(groups: tuple[str, ...], operation_id: str) -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_tool(permissions, 'engineering', ConnectorToolRef('inventory', 'getItem'))
    (service, _) = _service(store, permissions, events)
    assert await service.execute(_input(operation_id), groups) == _safe_unavailable()
    assert events == []

@pytest.mark.asyncio
@pytest.mark.parametrize('records,operation_id', [(None, 'getItem'), (_records(operation_id='other'), 'getItem')])
async def test_hidden_states_have_one_safe_outcome_and_no_downstream_calls(records: tuple[OpenApiConnector, OpenApiConnectorCatalog] | None, operation_id: str) -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    if records is not None:
        await _save(store, records)
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events)
    assert await service.execute(_input(operation_id), ('engineering',)) == _safe_unavailable()
    assert events == []

@pytest.mark.asyncio
async def test_connector_without_current_catalog_has_one_safe_outcome_and_no_downstream_calls() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    (connector, _) = _records()
    await store.save_connector(connector)
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events)
    assert await service.execute(_input(), ('engineering',)) == _safe_unavailable()
    assert events == []

@pytest.mark.asyncio
async def test_authorization_and_point_operation_read_precede_all_outbound_work() -> None:
    events: list[str] = []
    store = await RecordingStore.create(events)
    await _save(store, _records())
    service = OpenApiCapabilityExecutionService(store, RecordingAuthorizer(events, True), AggregateOpenApiOperationResolver(), RecordingCompiler(events), RecordingTransport(events), RecordingNormalizer(events), OpenApiExecutionLimits(timeout_seconds=1, maximum_response_bytes=5), UnauthenticatedOpenApiRequestAuthenticator(), create_tool_execution_pipeline(PermitAllConnectorInvocationPolicy(), ()))
    await service.execute(_input(), ('engineering',))
    assert events == ['authorize', 'operation-read', 'compile', 'transport', 'normalize']

@pytest.mark.asyncio
async def test_permission_and_catalog_changes_are_visible_on_next_call() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    (connector, catalog) = _records()
    await _save(store, (connector, catalog))
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events)
    assert (await service.execute(_input(), ('engineering',))).status == 'success'
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=()))
    assert await service.execute(_input(), ('engineering',)) == _safe_unavailable()
    await _grant_connector(permissions, 'engineering', 'inventory')
    assert (await service.execute(_input(), ('engineering',))).status == 'success'
    (_, replacement) = _records('cat-2', 'replacement')
    await store.save_catalog(replacement)
    assert await service.execute(_input(), ('engineering',)) == _safe_unavailable()

@pytest.mark.asyncio
async def test_missing_and_present_empty_json_bodies_reach_compiler_distinctly() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, compiler) = _service(store, permissions, events)
    await service.execute(_input(body=MissingJsonBody()), ('engineering',))
    await service.execute(_input(body=PresentJsonBody(value={})), ('engineering',))
    assert compiler.bodies == [MissingJsonBody(), PresentJsonBody(value={})]

@pytest.mark.asyncio
async def test_compiler_typed_validation_failure_is_non_leaking() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, compiler_failure=ValueError('secret-canary'))
    result = await service.execute(_input(), ('engineering',))
    assert result.code == 'invalid_arguments'
    assert 'secret-canary' not in result.model_dump_json()
    assert events == ['compile']

@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code', [(RuntimeError('secret'), 'outbound_failed'), (OutboundPolicyError(), 'destination_denied'), (OutboundRedirectError(), 'redirect_denied'), (OutboundTimeoutError(), 'outbound_timeout'), (OutboundNetworkError(), 'outbound_unavailable'), (OutboundTlsError(), 'outbound_tls_failed')])
async def test_transport_failures_map_to_stable_non_leaking_outcomes(failure: BaseException, code: str) -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, transport_failure=failure)
    result = await service.execute(_input(), ('engineering',))
    assert result.code == code
    assert 'secret' not in result.model_dump_json()

@pytest.mark.asyncio
async def test_normalized_success_reports_normalized_status_size_and_truncation() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events)
    result = await service.execute(_input(), ('engineering',))
    assert result.model_dump() == {'status': 'success', 'code': None, 'message': 'OpenAPI capability executed.', 'http_status': 202, 'content_type': 'application/json', 'response_size_bytes': 3, 'truncated': True}

@pytest.mark.asyncio
async def test_cancellation_propagates_without_outbound_normalize() -> None:
    events: list[str] = []
    store = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, _records())
    permissions = GroupPermissionStoreService(create_inmemory_runtime().database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE)
    await _grant_connector(permissions, 'engineering', 'inventory')
    (service, _) = _service(store, permissions, events, transport_failure=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await service.execute(_input(body=PresentJsonBody(value={'secret': 'canary'})), ('engineering',))
    assert 'normalize' not in events
