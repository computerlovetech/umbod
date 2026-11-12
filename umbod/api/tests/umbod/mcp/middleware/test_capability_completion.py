import asyncio
from collections.abc import Iterator
from dataclasses import dataclass

import mcp.types as mt
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import AuthorizationError, NotFoundError, PromptError, ResourceError, ValidationError
from fastmcp.resources.base import ResourceResult
from fastmcp.server.middleware import MiddlewareContext
from mcp.shared.exceptions import MCPError
from pydantic import TypeAdapter

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.diagnostics import ApplicationFailureKind, PublishingSignalFailureHandler
from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence
from umbod.core.signals import Signal
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter
from umbod.mcp.middleware.capability_completion import McpCapabilityCompletionMiddleware
from umbod.mcp.signals.capabilities import (
    McpCapabilityCompleted,
    McpCapabilityFailed,
    McpCapabilityFailureCategory,
    McpCapabilityMethod,
    McpPromptTarget,
    McpResourceTarget,
    prompt_target,
    resource_target,
)
from umbod.mcp.signals.context import McpInvocationContext, reset_mcp_invocation_context, set_mcp_invocation_context
from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation


@pytest.fixture(autouse=True)
def isolated_invocation_context() -> Iterator[None]:
    token = set_mcp_invocation_context(McpInvocationContext(
        actor=McpInvocationActor(),
        correlation=McpInvocationCorrelation('a' * 32, 'b' * 16),
        server_name='capability-completion-tests',
    ))
    try:
        yield
    finally:
        reset_mcp_invocation_context(token)


def serialize_completion(event: McpCapabilityCompleted) -> str:
    return TypeAdapter(McpCapabilityCompleted).dump_json(event).decode('utf-8')


class ManualClock:
    def __init__(self) -> None:
        self.now = 10.0
        self.failing = False

    def __call__(self) -> float:
        if self.failing:
            raise RuntimeError('private-observation-failure')
        return self.now


def timestamp() -> int:
    return 123456789


@dataclass
class Observation:
    middleware: McpCapabilityCompletionMiddleware
    signal: Signal[McpCapabilityCompleted]
    events: list[McpCapabilityCompleted]
    failures: CapturingApplicationFailures
    clock: ManualClock


def observation() -> Observation:
    failures = CapturingApplicationFailures()
    handler = PublishingSignalFailureHandler(failures)
    signal = Signal[McpCapabilityCompleted](handler)
    events: list[McpCapabilityCompleted] = []
    signal.connect('test.capture', events.append)
    clock = ManualClock()
    return Observation(
        McpCapabilityCompletionMiddleware(signal, McpAuditIdentityAdapter(), handler, clock, timestamp),
        signal, events, failures, clock,
    )


def resource_context() -> MiddlewareContext[mt.ReadResourceRequestParams]:
    return MiddlewareContext(
        message=mt.ReadResourceRequestParams(uri='data://private-resource/secret-identifier'),
        method='resources/read',
    )


async def invoke(client: Client, method: McpCapabilityMethod) -> object:
    match method:
        case McpCapabilityMethod.READ_RESOURCE:
            return await client.read_resource('data://private-resource/secret-identifier')
        case McpCapabilityMethod.GET_PROMPT:
            return await client.get_prompt('private_prompt', {'value': 'secret-argument'})
        case McpCapabilityMethod.LIST_RESOURCES:
            return await client.list_resources()
        case McpCapabilityMethod.LIST_RESOURCE_TEMPLATES:
            return await client.list_resource_templates()
        case McpCapabilityMethod.LIST_PROMPTS:
            return await client.list_prompts()


@pytest.mark.asyncio
@pytest.mark.parametrize('method', tuple(McpCapabilityMethod))
async def test_public_capability_operation_publishes_one_sanitized_completion(method: McpCapabilityMethod) -> None:
    observed = observation()
    server = FastMCP('capabilities', middleware=[observed.middleware])

    @server.resource('data://private-resource/{identifier}')
    async def read(identifier: str) -> str:
        return 'secret-content-' + identifier

    @server.prompt(name='private_prompt')
    async def prompt(value: str) -> str:
        return 'secret-content-' + value

    async with Client(server) as client:
        await invoke(client, method)

    assert len(observed.events) == 1
    event = observed.events[0]
    assert event.method == method
    assert event.outcome == 'success'
    assert event.duration_ms == 0
    assert event.started_at_unix_nano == 123456789
    assert len(event.correlation.trace_id) == 32
    if method == McpCapabilityMethod.READ_RESOURCE:
        assert isinstance(event.target, McpResourceTarget)
        assert event.target == resource_target('data://private-resource/secret-identifier')
    if method == McpCapabilityMethod.GET_PROMPT:
        assert isinstance(event.target, McpPromptTarget)
        assert event.target == prompt_target('private_prompt')
    serialized = serialize_completion(event)
    for secret in ('secret-content', 'secret-argument', 'secret-identifier', 'private-resource', 'private_prompt'):
        assert secret not in serialized
    assert observed.failures.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(('error', 'category'), [
    (AuthorizationError('secret-error'), McpCapabilityFailureCategory.AUTHORIZATION),
    (ValidationError('secret-error'), McpCapabilityFailureCategory.VALIDATION),
    (NotFoundError('secret-error'), McpCapabilityFailureCategory.NOT_FOUND),
    (RuntimeError('secret-error'), McpCapabilityFailureCategory.UNEXPECTED_ERROR),
    (ResourceError('secret-error'), McpCapabilityFailureCategory.UNEXPECTED_ERROR),
    (PromptError('secret-error'), McpCapabilityFailureCategory.UNEXPECTED_ERROR),
])
async def test_failure_preserves_original_exception_and_publishes_safe_evidence(
    error: Exception, category: McpCapabilityFailureCategory,
) -> None:
    observed = observation()

    async def fail(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        observed.clock.now += 0.25
        raise error

    with pytest.raises(type(error)) as raised:
        await observed.middleware.on_read_resource(resource_context(), fail)

    assert raised.value is error
    assert len(observed.events) == 1
    event = observed.events[0]
    assert isinstance(event.result, McpCapabilityFailed)
    assert event.result.category == category
    assert event.duration_ms == 250
    assert event.outcome == 'failure'
    assert 'secret-error' not in serialize_completion(event)
    if category == McpCapabilityFailureCategory.UNEXPECTED_ERROR:
        assert isinstance(event.result.evidence, InvocationExceptionEvidence)
        assert event.result.evidence.exception_type == type(error).__qualname__
        assert len(event.result.evidence.stacktrace) <= 4096
    else:
        assert event.result.evidence.origin == 'client_input'


@pytest.mark.asyncio
async def test_cancellation_publishes_once_without_replacing_cancellation() -> None:
    observed = observation()
    cancellation = asyncio.CancelledError('secret-cancellation')

    async def cancel(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        raise cancellation

    with pytest.raises(asyncio.CancelledError) as raised:
        await observed.middleware.on_read_resource(resource_context(), cancel)

    assert raised.value is cancellation
    assert [event.outcome for event in observed.events] == ['cancelled']
    assert 'secret-cancellation' not in serialize_completion(observed.events[0])


@pytest.mark.asyncio
async def test_failing_receiver_does_not_change_result_or_block_remaining_receivers() -> None:
    observed = observation()
    after_failure: list[McpCapabilityCompleted] = []

    def fail(event: McpCapabilityCompleted) -> None:
        raise RuntimeError('secret-receiver-error')

    observed.signal.connect('mcp.capability.logging', fail)
    observed.signal.connect('test.after_failure', after_failure.append)
    expected = ResourceResult('secret-result')

    async def succeed(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        return expected

    result = await observed.middleware.on_read_resource(resource_context(), succeed)

    assert result is expected
    assert after_failure == observed.events
    assert len(observed.failures.events) == 1
    failure = observed.failures.events[0]
    assert failure.kind == ApplicationFailureKind.SIGNAL_RECEIVER
    assert dict(failure.attributes)['receiver.name'] == 'mcp.capability.logging'
    assert 'secret-receiver-error' not in failure.model_dump_json()


@pytest.mark.asyncio
async def test_observation_setup_failure_does_not_prevent_execution() -> None:
    observed = observation()
    observed.clock.failing = True
    expected = ResourceResult('secret-result')

    async def succeed(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        return expected

    result = await observed.middleware.on_read_resource(resource_context(), succeed)

    assert result is expected
    assert observed.events == []
    assert len(observed.failures.events) == 1
    assert 'private-observation-failure' not in observed.failures.events[0].model_dump_json()


@pytest.mark.asyncio
async def test_concurrent_operations_retain_isolated_correlation() -> None:
    observed = observation()

    async def run(trace_id: str) -> None:
        token = set_mcp_invocation_context(McpInvocationContext(
            actor=McpInvocationActor(), correlation=McpInvocationCorrelation(trace_id), server_name='test',
        ))
        try:
            async def succeed(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
                await asyncio.sleep(0)
                return ResourceResult('secret-result')

            await observed.middleware.on_read_resource(resource_context(), succeed)
        finally:
            reset_mcp_invocation_context(token)

    await asyncio.gather(run('a' * 32), run('b' * 32))

    assert len(observed.events) == 2
    assert {event.correlation.trace_id for event in observed.events} == {'a' * 32, 'b' * 32}


@pytest.mark.asyncio
async def test_application_instances_do_not_share_completion_subscriptions() -> None:
    first = observation()
    second = observation()

    async def succeed(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        return ResourceResult('secret-result')

    await first.middleware.on_read_resource(resource_context(), succeed)

    assert len(first.events) == 1
    assert second.events == []


class UnavailablePublisher:
    def send(self, event: McpCapabilityCompleted) -> None:
        raise RuntimeError('secret-publisher-failure')


@pytest.mark.asyncio
@pytest.mark.parametrize('operation_fails', [False, True])
async def test_publication_failure_preserves_operation_outcome(operation_fails: bool) -> None:
    failures = CapturingApplicationFailures()
    middleware = McpCapabilityCompletionMiddleware(
        UnavailablePublisher(), McpAuditIdentityAdapter(), PublishingSignalFailureHandler(failures),
        ManualClock(), timestamp,
    )
    expected = ResourceResult('secret-result')
    error = RuntimeError('secret-operation-failure')

    async def execute(context: MiddlewareContext[mt.ReadResourceRequestParams]) -> ResourceResult:
        if operation_fails:
            raise error
        return expected

    if operation_fails:
        with pytest.raises(RuntimeError) as raised:
            await middleware.on_read_resource(resource_context(), execute)
        assert raised.value is error
    else:
        assert await middleware.on_read_resource(resource_context(), execute) is expected
    assert len(failures.events) == 1
    assert 'secret-publisher-failure' not in failures.events[0].model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize('method', [McpCapabilityMethod.READ_RESOURCE, McpCapabilityMethod.GET_PROMPT])
async def test_unknown_target_failure_is_observed_at_public_resolution_boundary(method: McpCapabilityMethod) -> None:
    observed = observation()
    server = FastMCP('empty', middleware=[observed.middleware])

    async with Client(server) as client:
        with pytest.raises(MCPError):
            await invoke(client, method)

    assert len(observed.events) == 1
    assert observed.events[0].method == method
    assert isinstance(observed.events[0].result, McpCapabilityFailed)
    assert observed.events[0].result.category == McpCapabilityFailureCategory.NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize('arguments', [{}, {'value': 'secret-invalid-number'}])
async def test_public_prompt_argument_validation_is_a_client_rejection(arguments: dict[str, str]) -> None:
    observed = observation()
    server = FastMCP('prompt-validation', middleware=[observed.middleware])
    executions: list[int] = []

    @server.prompt(name='integer_prompt')
    async def prompt(value: int) -> str:
        executions.append(value)
        return str(value)

    async with Client(server) as client:
        with pytest.raises(MCPError):
            await client.get_prompt('integer_prompt', arguments)

    assert executions == []
    assert len(observed.events) == 1
    result = observed.events[0].result
    assert isinstance(result, McpCapabilityFailed)
    assert result.category == McpCapabilityFailureCategory.VALIDATION
    assert result.evidence.origin == 'client_input'
    assert 'secret-invalid-number' not in serialize_completion(observed.events[0])


@pytest.mark.asyncio
async def test_value_error_inside_prompt_execution_remains_an_unexpected_failure() -> None:
    observed = observation()
    server = FastMCP('prompt-execution', middleware=[observed.middleware])

    @server.prompt(name='failing_prompt')
    async def prompt(value: str) -> str:
        raise ValueError('secret-execution-error')

    async with Client(server) as client:
        with pytest.raises(MCPError):
            await client.get_prompt('failing_prompt', {'value': 'secret-argument'})

    assert len(observed.events) == 1
    result = observed.events[0].result
    assert isinstance(result, McpCapabilityFailed)
    assert result.category == McpCapabilityFailureCategory.UNEXPECTED_ERROR
    assert 'secret-execution-error' not in serialize_completion(observed.events[0])


def test_target_fingerprints_have_separate_resource_and_prompt_domains() -> None:
    assert resource_target('same').uri_fingerprint != prompt_target('same').name_fingerprint
