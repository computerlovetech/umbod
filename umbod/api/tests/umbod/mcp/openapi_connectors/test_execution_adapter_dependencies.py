import asyncio
from types import SimpleNamespace
from typing import Callable, Literal
from unittest.mock import AsyncMock, create_autospec

import pytest

from umbod.core.connectors.openapi.execution import (
    AsyncStreamingHttpClient,
    OpenApiCapabilityExecutionResult,
    OpenApiExecutionResponse,
    OpenApiOperationInput,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.invocation.tools.execution import ToolExecutionPipeline
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.connectors.native.tools.deployment_modes.codemode import OpenApiCodeModeInvocation
from umbod.mcp.connectors.openapi import OpenApiCodeModeExecutionAdapter
from umbod.mcp.signals import McpToolExecutionPipelineFactory


FailureStage = Literal['none', 'factory', 'execution', 'cancel_factory', 'cancel_execution']


class RecordingExecutionService:
    def __init__(self, failure: FailureStage, entered: asyncio.Event, release: asyncio.Event) -> None:
        self._failure = failure
        self._entered = entered
        self._release = release
        self.inputs: list[OpenApiOperationInput] = []

    async def execute(
        self, operation_input: OpenApiOperationInput, groups: tuple[str, ...]
    ) -> OpenApiCapabilityExecutionResult:
        self.inputs.append(operation_input)
        self._entered.set()
        await self._release.wait()
        if self._failure == 'execution':
            raise RuntimeError('execution failed')
        return OpenApiCapabilityExecutionResult(status='success', message=operation_input.operation_id)


class RecordingExecutionServiceFactory:
    def __init__(self, failure: FailureStage, entered: asyncio.Event, release: asyncio.Event) -> None:
        self._failure = failure
        self._entered = entered
        self._release = release
        self.resources: list[tuple[
            OpenApiConnectorStore, GroupPermissionReader, AsyncStreamingHttpClient,
            ToolExecutionPipeline[OpenApiExecutionResponse],
        ]] = []
        self.services: list[RecordingExecutionService] = []

    async def create(
        self,
        store: OpenApiConnectorStore,
        permission_reader: GroupPermissionReader,
        client: AsyncStreamingHttpClient,
        execution_pipeline: ToolExecutionPipeline[OpenApiExecutionResponse],
    ) -> RecordingExecutionService:
        self.resources.append((store, permission_reader, client, execution_pipeline))
        if self._failure == 'factory':
            raise RuntimeError('factory failed')
        if self._failure == 'cancel_factory':
            self._entered.set()
            await self._release.wait()
        service = RecordingExecutionService(self._failure, self._entered, self._release)
        self.services.append(service)
        return service


class AdapterHarness:
    def __init__(self, failure: FailureStage) -> None:
        self.closed: list[str] = []
        self.stores: list[SimpleNamespace] = []
        self.readers: list[SimpleNamespace] = []
        self.clients: list[SimpleNamespace] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.factory = RecordingExecutionServiceFactory(failure, self.entered, self.release)
        self.pipelines = create_autospec(McpToolExecutionPipelineFactory, instance=True)
        self.created_pipelines: list[ToolExecutionPipeline[OpenApiExecutionResponse]] = []
        self.pipelines.create.side_effect = self.create_pipeline
        server = SimpleNamespace(
            auth=None,
            permission_group_claim='groups',
            openapi_connector_store_factory=SimpleNamespace(create=self.create_store),
            group_permission_reader_factory=SimpleNamespace(create=self.create_reader),
            openapi_outbound_http_client_factory=SimpleNamespace(create=self.create_client),
        )
        self.adapter = OpenApiCodeModeExecutionAdapter(server, self.pipelines, self.factory)

    def create_pipeline(
        self, connector_name: str, is_error: Callable[[object], bool]
    ) -> ToolExecutionPipeline[OpenApiExecutionResponse]:
        pipeline = create_autospec(ToolExecutionPipeline, instance=True)
        self.created_pipelines.append(pipeline)
        return pipeline

    async def create_store(self) -> SimpleNamespace:
        store = SimpleNamespace(
            get_connector=AsyncMock(return_value=SimpleNamespace(display_name='API')),
            close=lambda: self.closed.append('store'),
        )
        self.stores.append(store)
        return store

    async def create_reader(self) -> SimpleNamespace:
        reader = SimpleNamespace(close=lambda: self.closed.append('reader'))
        self.readers.append(reader)
        return reader

    def create_client(self) -> SimpleNamespace:
        async def close() -> None:
            self.closed.append('client')

        client = SimpleNamespace(aclose=close)
        self.clients.append(client)
        return client

    async def execute(self, operation_id: str) -> object:
        return await self.adapter.execute(OpenApiCodeModeInvocation(
            connector_id='api', operation_id=operation_id, path={'id': '1'},
            query={'page': 2}, headers={'X-Test': 'value'}, body={'value': {'name': 'input'}},
        ))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['none', 'factory', 'execution', 'cancel_factory', 'cancel_execution'])
async def test_execution_closes_borrowed_resources_in_order(failure: FailureStage) -> None:
    harness = AdapterHarness(failure)
    if failure.startswith('cancel_'):
        task = asyncio.create_task(harness.execute('first'))
        await asyncio.wait_for(harness.entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        harness.release.set()
        if failure == 'none':
            result = await harness.execute('first')
            assert result == OpenApiCapabilityExecutionResult(status='success', message='first').model_dump(mode='json')
        else:
            with pytest.raises(RuntimeError, match=f'{failure} failed'):
                await harness.execute('first')

    assert harness.closed == ['client', 'reader', 'store']


@pytest.mark.asyncio
@pytest.mark.parametrize('overlapping', [False, True])
async def test_each_execution_passes_its_resources_and_pipeline_to_a_fresh_service(overlapping: bool) -> None:
    harness = AdapterHarness('none')
    if overlapping:
        first = asyncio.create_task(harness.execute('first'))
        await asyncio.wait_for(harness.entered.wait(), timeout=1)
        harness.entered.clear()
        second = asyncio.create_task(harness.execute('second'))
        await asyncio.wait_for(harness.entered.wait(), timeout=1)
        harness.release.set()
        await asyncio.gather(first, second)
    else:
        harness.release.set()
        await harness.execute('first')
        await harness.execute('second')

    assert len(harness.factory.services) == 2
    assert harness.factory.services[0] is not harness.factory.services[1]
    for index, operation_id in enumerate(('first', 'second')):
        store, reader, client, pipeline = harness.factory.resources[index]
        assert store is harness.stores[index]
        assert reader is harness.readers[index]
        assert client is harness.clients[index]
        assert pipeline is harness.created_pipelines[index]
        operation_input = harness.factory.services[index].inputs[0]
        assert operation_input.connector_id == 'api'
        assert operation_input.operation_id == operation_id
        assert operation_input.path == {'id': '1'}
        assert operation_input.query == {'page': 2}
        assert operation_input.headers == {'X-Test': 'value'}
        assert operation_input.body.value == {'name': 'input'}
    assert harness.factory.resources[0][3] is not harness.factory.resources[1][3]
    assert harness.pipelines.create.call_count == 2
