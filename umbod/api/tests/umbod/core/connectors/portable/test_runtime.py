from asyncio import CancelledError, Event, create_task, wait_for
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic_monty import AsyncMonty
from umbod_sdk.connectors.api.http import HttpPostRequest, HttpRequest, RawHttpResponse

from umbod.core.connectors.portable import (
    PortableConnectorRuntime,
    PortableExecutionError,
    PortableExecutionLimits,
    PortableHttpAccess,
)
from umbod.infrastructure.portable_connectors import MontyPortableSandbox, portable_sdk_mount


pytestmark = pytest.mark.asyncio

_FIXTURES = Path(__file__).with_name("fixtures")
_ISSUE_PATH = ("projects", "42", "issues")
_DENIED = PortableHttpAccess(frozenset(), frozenset())
_READ = PortableHttpAccess(frozenset({"tracker"}), frozenset())
_WRITE = PortableHttpAccess(frozenset({"tracker"}), frozenset({("tracker", _ISSUE_PATH)}))
_LIMITS = PortableExecutionLimits(deadline_seconds=4, max_http_calls=8)


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []
        self.replies: deque[RawHttpResponse | Exception] = deque()

    async def send(self, request: HttpRequest) -> RawHttpResponse:
        self.requests.append(request)
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


class GatedTransport:
    def __init__(self) -> None:
        self.started = {project: Event() for project in ("42", "43")}
        self.cancelled = {project: Event() for project in self.started}
        self.release = Event()

    async def send(self, request: HttpRequest) -> RawHttpResponse:
        project = request.path[1]
        self.started[project].set()
        try:
            await self.release.wait()
        except CancelledError:
            self.cancelled[project].set()
            raise
        return RawHttpResponse(200, b"[7]")


@pytest_asyncio.fixture
async def sandbox() -> AsyncIterator[MontyPortableSandbox]:
    with portable_sdk_mount() as mount:
        async with AsyncMonty(max_processes=2) as pool:
            yield MontyPortableSandbox(pool, mount)


@pytest.fixture
def transport() -> RecordingTransport:
    return RecordingTransport()


@pytest.fixture
def runtime(sandbox: MontyPortableSandbox, transport: RecordingTransport) -> PortableConnectorRuntime:
    return PortableConnectorRuntime(sandbox, transport, _LIMITS)


def _source(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


async def test_preparation_and_invocation_loading_cannot_send(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    source = _source("issue_tracker.py") + """
from umbod_http_binding import dispatch
assert (await dispatch({"target": "tracker", "method": "GET", "path": ["projects", "42"], "query": [], "response_mode": "status"})) == {"error": "invocation_closed"}
"""
    prepared = await runtime.prepare(source)
    transport.replies.append(RawHttpResponse(200, b"no body needed"))

    assert prepared.manifest["manifest_version"] == 2
    assert await runtime.check_configuration(prepared, {"project": "42"}, _READ)
    assert len(transport.requests) == 1


async def test_configuration_check_and_read_use_validated_relative_requests(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))
    transport.replies.extend((RawHttpResponse(200, b"not JSON"), RawHttpResponse(200, b"[7]")))

    assert await runtime.check_configuration(prepared, {"project": "42"}, _READ)
    assert await runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _READ) == {
        "status": 200, "body": {"kind": "json", "value": [7]},
    }
    assert transport.requests == [
        HttpRequest("tracker", "GET", ("projects", "42"), (), "status"),
        HttpRequest("tracker", "GET", _ISSUE_PATH, (("label", "open"), ("label", "support")), "json"),
    ]


async def test_declared_target_without_host_approval_cannot_send(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    assert await runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _DENIED) == {"error": "unknown_target"}
    assert not transport.requests


@pytest.mark.parametrize("access", [_READ, PortableHttpAccess(frozenset({"tracker"}), frozenset({("tracker", _ISSUE_PATH[:-1])}))])
async def test_post_without_exact_grant_cannot_send(
    runtime: PortableConnectorRuntime, transport: RecordingTransport, access: PortableHttpAccess
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    assert await runtime.invoke_tool(prepared, "create", {"project": "42"}, {"title": "Fix"}, access) == {
        "error": "policy_denied",
    }
    assert not transport.requests


async def test_exact_post_grant_sends_validated_json(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))
    transport.replies.append(RawHttpResponse(201, b"hidden"))

    assert await runtime.invoke_tool(prepared, "create", {"project": "42"}, {"title": "Fix"}, _WRITE) == {
        "status": 201, "body": {"kind": "no_content"},
    }
    assert transport.requests == [HttpPostRequest("tracker", "POST", _ISSUE_PATH, (), "status", b'{"title":"Fix"}')]


async def test_post_transport_timeout_reports_unknown_without_retry(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))
    transport.replies.append(TimeoutError("upstream diagnostic"))

    assert await runtime.invoke_tool(prepared, "create", {"project": "42"}, {"title": "Fix"}, _WRITE) == {
        "error": "outcome_unknown",
    }
    assert len(transport.requests) == 1


async def test_invalid_upstream_json_is_not_exposed(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))
    transport.replies.append(RawHttpResponse(200, b'["private value"]'))

    assert await runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _READ) == {
        "error": "response_contract_mismatch",
    }


async def test_invalid_invocation_is_rejected_before_transport(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    with pytest.raises(PortableExecutionError, match="Invalid portable configuration"):
        await runtime.check_configuration(prepared, {}, _READ)
    with pytest.raises(PortableExecutionError, match="Invalid portable tool arguments"):
        await runtime.invoke_tool(prepared, "read", {"project": "42"}, {"context": "override"}, _READ)
    with pytest.raises(PortableExecutionError, match="Unknown portable connector operation"):
        await runtime.invoke_tool(prepared, "missing", {"project": "42"}, {}, _READ)
    assert not transport.requests


async def test_preparation_rejects_non_manifest(runtime: PortableConnectorRuntime, transport: RecordingTransport) -> None:
    with pytest.raises(PortableExecutionError, match="Invalid portable connector manifest"):
        await runtime.prepare(_source("greeting.py") + "\nconnector.manifest = lambda: {'manifest_version': True}")
    assert not transport.requests


async def test_runtime_rejects_different_source_even_with_the_same_manifest(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    prepared = await runtime.prepare(_source("greeting.py"))
    different = replace(prepared, source=prepared.source.replace(' + ", " + ', ' + "! " + '))

    with pytest.raises(PortableExecutionError, match="source changed"):
        await runtime.invoke_tool(different, "greet", {"prefix": "Hello"}, {"name": "Ada"}, _DENIED)
    assert not transport.requests


async def test_sandbox_recursion_budget_rejects_loading(
    runtime: PortableConnectorRuntime, transport: RecordingTransport
) -> None:
    source = _source("greeting.py") + "\ndef recurse():\n    return recurse()\nrecurse()\n"

    with pytest.raises(PortableExecutionError, match="Could not load"):
        await runtime.prepare(source)
    assert not transport.requests


async def test_invalid_check_result_is_sanitized(runtime: PortableConnectorRuntime) -> None:
    source = _source("greeting.py").replace('return bool(configuration["prefix"])', 'return "private value"')
    prepared = await runtime.prepare(source)

    with pytest.raises(PortableExecutionError, match="^Invalid portable configuration check result$"):
        await runtime.check_configuration(prepared, {"prefix": "Hello"}, _DENIED)


async def test_tool_output_schema_is_enforced(runtime: PortableConnectorRuntime) -> None:
    source = _source("greeting.py").replace('output_schema={"type": "string"}', 'output_schema={"type": "integer"}')
    prepared = await runtime.prepare(source)

    with pytest.raises(PortableExecutionError, match="^Invalid portable tool output$"):
        await runtime.invoke_tool(prepared, "greet", {"prefix": "Hello"}, {"name": "Ada"}, _DENIED)


@pytest.mark.parametrize(
    "title, error",
    [("", "request_contract_mismatch"), ("x" * (1024 * 1024), "limit_exceeded")],
    ids=["schema-mismatch", "body-too-large"],
)
async def test_invalid_post_bodies_are_not_sent(
    runtime: PortableConnectorRuntime, transport: RecordingTransport, title: str, error: str
) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    assert await runtime.invoke_tool(prepared, "create", {"project": "42"}, {"title": title}, _WRITE) == {"error": error}
    assert not transport.requests


async def test_path_rejected_before_transport(runtime: PortableConnectorRuntime, transport: RecordingTransport) -> None:
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    assert await runtime.invoke_tool(prepared, "read", {"project": ".."}, {}, _READ) == {"error": "invalid_request"}
    assert not transport.requests


async def test_host_call_budget_rejects_extra_requests(
    sandbox: MontyPortableSandbox, transport: RecordingTransport
) -> None:
    source = _source("issue_tracker.py").replace(
        "    return await context.request(",
        '    await context.request_status("tracker", path=["projects"], query=[])\n    return await context.request(',
    )
    runtime = PortableConnectorRuntime(sandbox, transport, PortableExecutionLimits(4, 1))
    prepared = await runtime.prepare(source)
    transport.replies.append(RawHttpResponse(200, b"unused"))

    assert await runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _READ) == {"error": "limit_exceeded"}
    assert len(transport.requests) == 1


async def test_execution_deadline_cancels_pending_transport(sandbox: MontyPortableSandbox) -> None:
    transport = GatedTransport()
    runtime = PortableConnectorRuntime(sandbox, transport, PortableExecutionLimits(1, 8))
    prepared = await runtime.prepare(_source("issue_tracker.py"))

    with pytest.raises(PortableExecutionError, match="execution timed out"):
        await runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _READ)
    assert transport.cancelled["42"].is_set()


async def test_v1_tool_runs_without_http(runtime: PortableConnectorRuntime, transport: RecordingTransport) -> None:
    prepared = await runtime.prepare(_source("greeting.py"))

    assert prepared.manifest["manifest_version"] == 1
    assert await runtime.invoke_tool(prepared, "greet", {"prefix": "Hello"}, {"name": "Ada"}, _DENIED) == "Hello, Ada"
    assert not transport.requests


async def test_cancelling_one_invocation_only_drains_its_request(sandbox: MontyPortableSandbox) -> None:
    transport = GatedTransport()
    runtime = PortableConnectorRuntime(sandbox, transport, _LIMITS)
    prepared = await runtime.prepare(_source("issue_tracker.py"))
    first = create_task(runtime.invoke_tool(prepared, "read", {"project": "42"}, {}, _READ))
    second = create_task(runtime.invoke_tool(prepared, "read", {"project": "43"}, {}, _READ))
    try:
        for started in transport.started.values():
            await wait_for(started.wait(), timeout=2)
        first.cancel()
        with pytest.raises(CancelledError):
            await first
        assert transport.cancelled["42"].is_set()
        assert not transport.cancelled["43"].is_set()
        transport.release.set()
        assert await second == {"status": 200, "body": {"kind": "json", "value": [7]}}
    finally:
        transport.release.set()
        for task in (first, second):
            if not task.done():
                task.cancel()
                with pytest.raises(CancelledError):
                    await task
