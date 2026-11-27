import asyncio
from collections import deque
from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from pydantic_monty import AsyncMonty, ExternalModule, MountDir

from umbod_sdk.connectors import Connector
from umbod_sdk.connectors.api.http import HttpPolicyDenied, HttpPostRequest, HttpRequest, HttpRequestBoundary, RawHttpResponse
from umbod_sdk.connectors.api.http_scope import HttpInvocation
from umbod_sdk.connectors.api.manifest import validate_manifest_schemas
from umbod_sdk.connectors.http import HttpContext


CONNECTOR_FILE = Path(__file__).with_name("fixtures") / "portable_http.py"
CONFIGURATION = {"project": "42"}
TARGETS = {"issue_tracker": "Read and create issues in a configured tracker."}
POST_PATH = ("projects", "42", "issues")
POST_APPROVAL = (("issue_tracker", POST_PATH),)


class RecordedTransport:
    def __init__(self, replies: list[RawHttpResponse | Exception]) -> None:
        self.requests: list[HttpRequest] = []
        self._replies = deque(replies)

    async def send(self, request: HttpRequest) -> RawHttpResponse:
        self.requests.append(request)
        reply = self._replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def _connector(*, http_targets: dict[str, str], input_schema: dict[str, Any]) -> Connector:
    connector = Connector(
        id="http_declaration",
        name="HTTP declaration",
        description="Read data.",
        capability_description="Read upstream data.",
        configuration={},
        http_targets=http_targets,
    )

    @connector.configuration_check
    def check_configuration() -> bool:
        return True

    @connector.tool(name="read", description="Read a record.", input_schema=input_schema)
    def read_record() -> str:
        return "record"

    return connector


def test_http_manifest_uses_version_two_without_destination_or_credentials() -> None:
    targets = dict(TARGETS)
    connector = _connector(http_targets=targets, input_schema={})
    targets["extra"] = "Ignore later author mutations."
    manifest = connector.manifest()

    assert manifest["manifest_version"] == 2
    assert manifest["http_targets"] == TARGETS
    manifest["http_targets"].clear()
    assert connector.manifest()["http_targets"] == TARGETS


def test_empty_http_targets_keep_the_version_one_shape() -> None:
    manifest = _connector(http_targets={}, input_schema={}).manifest()

    assert manifest["manifest_version"] == 1
    assert "http_targets" not in manifest


@pytest.mark.parametrize(
    "targets",
    [
        {"https://example.invalid": "A URL cannot be an ID."},
        {"api": "  "},
        {"a" * 65: "A target."},
        {"api": "a" * 257},
        {f"target_{index}": "A target." for index in range(17)},
    ],
)
def test_invalid_http_targets_are_rejected_at_declaration(targets: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="HTTP target|http_targets"):
        _connector(http_targets=targets, input_schema={})


@pytest.mark.parametrize(
    "input_schema",
    [
        {"allOf": [{"properties": {"context": {"type": "string"}}}]},
        {
            "$defs": {"args": {"properties": {"safe": {"type": "string"}}}},
            "allOf": [
                {
                    "$id": "https://schemas.example.invalid/nested",
                    "$defs": {"args": {"properties": {"context": {"type": "string"}}}},
                    "$ref": "#/$defs/args",
                },
            ],
        },
    ],
)
def test_manifest_version_two_reserves_context_in_composed_tool_schema(input_schema: dict[str, Any]) -> None:
    connector = _connector(http_targets=TARGETS, input_schema=input_schema)

    with pytest.raises(ValueError, match="reserved 'context' parameter"):
        connector.manifest()


def test_manifest_version_one_can_still_expose_context_as_a_public_argument() -> None:
    schema = {"properties": {"context": {"type": "string"}}}
    manifest = _connector(http_targets={}, input_schema=schema).manifest()

    assert manifest["tools"][0]["input_schema"] == schema


@pytest.mark.parametrize(
    "overrides",
    [{"manifest_version": 1}, {"manifest_version": 3}, {"manifest_version": True}, {"http_targets": {}}],
)
def test_host_rejects_invalid_http_manifest_version_or_targets(overrides: dict[str, Any]) -> None:
    manifest = _connector(http_targets=TARGETS, input_schema={}).manifest()

    with pytest.raises(ValueError, match="manifest_version|manifest version"):
        validate_manifest_schemas(manifest | overrides)


def test_same_http_connector_validates_contract_and_runs_in_cpython_and_monty(sdk_mount: MountDir) -> None:
    namespace = run_path(str(CONNECTOR_FILE))
    connector = namespace["connector"]
    manifest = connector.manifest()
    replies = [
        RawHttpResponse(status=200, body=b"not JSON; status checks never disclose the body"),
        RawHttpResponse(status=200, body=b'[{"id":1,"title":"A report","future_field":true}]'),
        RawHttpResponse(status=200, body=b'[{"id":"wrong","title":"A report"}]'),
    ]
    local_transport = RecordedTransport(replies)
    sandbox_transport = RecordedTransport(replies)

    async def verify() -> None:
        local_boundary = HttpRequestBoundary(targets=manifest["http_targets"], transport=local_transport)
        local_context = HttpContext(dispatch=local_boundary.dispatch)
        local_check = await namespace["check_tracker"](configuration=CONFIGURATION, context=local_context)
        local_results = [await namespace["read_issues"](configuration=CONFIGURATION, context=local_context) for _ in range(2)]

        async with AsyncMonty() as pool:
            sandbox_boundary = HttpRequestBoundary(targets=manifest["http_targets"], transport=sandbox_transport)
            modules = {"http_binding": ExternalModule({"dispatch": sandbox_boundary.dispatch})}
            async with pool.checkout(external_modules=modules) as session:
                await session.feed_run(
                    "import umbod_sdk.connectors\nimport umbod_sdk.connectors.http", mount=sdk_mount, cwd="/sdk"
                )
                await session.feed_run(CONNECTOR_FILE.read_text())
                sandbox_manifest = validate_manifest_schemas(await session.feed_run("connector.manifest()"))
                assert sandbox_manifest == manifest
                assert not sandbox_transport.requests
                await session.feed_run("from http_binding import dispatch\ncontext = HttpContext(dispatch=dispatch)")
                check_id = manifest["configuration_check_handler_id"]
                tool_id = manifest["tools"][0]["handler_id"]
                invocation = "await connector._handler(handler_id)(configuration=configuration, context=context)"
                sandbox_check = await session.feed_run(invocation, inputs={"handler_id": check_id, "configuration": CONFIGURATION})
                sandbox_results = [
                    await session.feed_run(invocation, inputs={"handler_id": tool_id, "configuration": CONFIGURATION})
                    for _ in range(2)
                ]

        assert local_check is sandbox_check is True
        assert local_results == sandbox_results == [
            {"status": 200, "body": {"kind": "json", "value": [{"id": 1, "title": "A report", "future_field": True}]}},
            {"error": "response_contract_mismatch"},
        ]
        assert local_transport.requests == sandbox_transport.requests == [
            HttpRequest(target="issue_tracker", method="GET", path=("projects", "42"), query=(), response_mode="status"),
            *[
                HttpRequest(
                    target="issue_tracker",
                    method="GET",
                    path=("projects", "42", "issues"),
                    query=(("label", "open"), ("label", "customer support")),
                    response_mode="json",
                )
            ] * 2,
        ]

    asyncio.run(verify())


def _request() -> dict[str, Any]:
    return {
        "target": "issue_tracker",
        "method": "GET",
        "path": ["projects", "42", "issues"],
        "query": [],
        "response_mode": "json",
        "response_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    }


@pytest.mark.parametrize(
    "updates,error",
    [
        ({"target": "undeclared"}, "unknown_target"),
        ({"method": "POST"}, "invalid_request"),
        ({"method": "PUT"}, "invalid_request"),
        ({"json_body": {}}, "invalid_request"),
        ({"path": ["https://wrong.invalid"]}, "invalid_request"),
        ({"path": ["//wrong.invalid"]}, "invalid_request"),
        ({"path": ["projects", ".."]}, "invalid_request"),
        ({"path": ["projects", "%2f"]}, "invalid_request"),
        ({"path": ["projects", "tasks?"]}, "invalid_request"),
        ({"path": ["projects", "path\\name"]}, "invalid_request"),
        ({"path": ["a" * 2049]}, "limit_exceeded"),
        ({"query": [["", "value"]]}, "invalid_request"),
        ({"query": [["key", "á" * 1000]]}, "limit_exceeded"),
        ({"headers": {"Authorization": "no"}}, "invalid_request"),
        ({"response_schema": {}}, "invalid_request"),
        ({"response_schema": {"type": "invalid"}}, "invalid_request"),
        ({"response_schema": {"type": "string", "pattern": "a+"}}, "invalid_request"),
        ({"response_schema": {"type": "string", "description": "a" * 16_385}}, "limit_exceeded"),
    ],
)
def test_invalid_request_never_reaches_transport(updates: dict[str, Any], error: str) -> None:
    transport = RecordedTransport([])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport)

    assert asyncio.run(boundary.dispatch(_request() | updates)) == {"error": error}
    assert not transport.requests


def test_json_request_without_response_schema_is_denied_before_dispatch() -> None:
    transport = RecordedTransport([])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport)
    request = _request()
    request.pop("response_schema")

    assert asyncio.run(boundary.dispatch(request)) == {"error": "invalid_request"}
    assert not transport.requests


@pytest.mark.parametrize(
    "reply,expected",
    [
        (RawHttpResponse(status=200, body=b'{"id": 5}'), {"status": 200, "body": {"kind": "json", "value": {"id": 5}}}),
        (RawHttpResponse(status=200, body=b'{"id": "5"}'), {"error": "response_contract_mismatch"}),
        (RawHttpResponse(status=200, body=b'{}'), {"error": "response_contract_mismatch"}),
        (RawHttpResponse(status=200, body=b'broken'), {"error": "invalid_response"}),
        (RawHttpResponse(status=200, body=b'{"id": NaN}'), {"error": "invalid_response"}),
        (RawHttpResponse(status=200, body=b'x' * 1_048_577), {"error": "limit_exceeded"}),
        (RawHttpResponse(status=204, body=b'ignored'), {"status": 204, "body": {"kind": "no_content"}}),
        (RawHttpResponse(status=404, body=b'{"secret":"ignored"}'), {"status": 404, "body": {"kind": "no_content"}}),
        (RawHttpResponse(status=302, body=b''), {"error": "redirect_disallowed"}),
        (RawHttpResponse(status=199, body=b''), {"error": "invalid_response"}),
        (HttpPolicyDenied("private binding details"), {"error": "policy_denied"}),
        (TimeoutError("private timeout details"), {"error": "timeout"}),
        (RuntimeError("private network details"), {"error": "transport_error"}),
    ],
)
def test_response_is_validated_or_sanitized_before_returning_to_connector(
    reply: RawHttpResponse | Exception, expected: dict[str, Any]
) -> None:
    transport = RecordedTransport([reply])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport)

    assert asyncio.run(boundary.dispatch(_request())) == expected
    assert len(transport.requests) == 1


def test_response_schema_can_use_in_document_references() -> None:
    transport = RecordedTransport([RawHttpResponse(status=200, body=b'{"id": 5}')])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport)
    schema = {
        "$ref": "#/$defs/item",
        "$defs": {"item": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    }

    response = asyncio.run(boundary.dispatch(_request() | {"response_schema": schema}))

    assert response == {"status": 200, "body": {"kind": "json", "value": {"id": 5}}}


def test_external_schema_reference_is_rejected_without_network_or_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_schema_fetch(url: object) -> None:
        pytest.fail(f"unexpected schema fetch: {url}")

    monkeypatch.setattr("urllib.request.urlopen", reject_schema_fetch)
    transport = RecordedTransport([])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport)
    schema = {"$ref": "https://schemas.example.invalid/response"}

    assert asyncio.run(boundary.dispatch(_request() | {"response_schema": schema})) == {"error": "invalid_request"}
    assert not transport.requests


def _post_request() -> dict[str, Any]:
    return _request() | {"method": "POST", "json_body": {"title": "Issue"}, "request_schema": {"type": "object"}}


@pytest.mark.parametrize(
    "path,approvals",
    [(POST_PATH, ()), ((*POST_PATH, "extra"), POST_APPROVAL), (POST_PATH, (("other_target", POST_PATH),))],
)
def test_post_requires_explicit_exact_path_approval(
    path: tuple[str, ...], approvals: tuple[tuple[str, tuple[str, ...]], ...]
) -> None:
    transport = RecordedTransport([])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport, approved_post_paths=approvals)

    assert asyncio.run(boundary.dispatch(_post_request() | {"path": list(path)})) == {"error": "policy_denied"}
    assert not transport.requests


@pytest.mark.parametrize(
    "updates,error",
    [
        ({"json_body": b"raw body"}, "invalid_request"),
        ({"json_body": {1: "invalid key"}}, "invalid_request"),
        ({"json_body": {"number": float("inf")}}, "invalid_request"),
        ({"json_body": []}, "request_contract_mismatch"),
        ({"request_schema": {"$ref": "https://schemas.example.invalid/body"}}, "invalid_request"),
        ({"json_body": {"title": "é" * 524_288}}, "limit_exceeded"),
    ],
)
def test_invalid_post_body_never_reaches_transport(updates: dict[str, Any], error: str) -> None:
    transport = RecordedTransport([])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport, approved_post_paths=POST_APPROVAL)

    assert asyncio.run(boundary.dispatch(_post_request() | updates)) == {"error": error}
    assert not transport.requests


@pytest.mark.parametrize(
    "reply,expected",
    [
        (TimeoutError("private timeout"), {"error": "outcome_unknown"}),
        (RuntimeError("private transport failure"), {"error": "outcome_unknown"}),
        (HttpPolicyDenied("private binding"), {"error": "policy_denied"}),
        (RawHttpResponse(201, b'{"id":"wrong"}'), {"error": "response_contract_mismatch"}),
        (RawHttpResponse(204, b""), {"status": 204, "body": {"kind": "no_content"}}),
        (RawHttpResponse(307, b""), {"error": "redirect_disallowed"}),
    ],
)
def test_post_reply_is_handled_without_replay(reply: RawHttpResponse | Exception, expected: dict[str, Any]) -> None:
    transport = RecordedTransport([reply])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport, approved_post_paths=POST_APPROVAL)

    assert asyncio.run(boundary.dispatch(_post_request())) == expected
    assert len(transport.requests) == 1


def test_status_only_post_can_send_json_null_without_exposing_response_body() -> None:
    transport = RecordedTransport([RawHttpResponse(201, b"ignored")])
    boundary = HttpRequestBoundary(targets=TARGETS, transport=transport, approved_post_paths=POST_APPROVAL)
    context = HttpContext(dispatch=boundary.dispatch)

    result = asyncio.run(context.post_status(
        "issue_tracker", path=list(POST_PATH), query=[], json_body=None, request_schema={"type": "null"}
    ))

    assert result == {"status": 201, "body": {"kind": "no_content"}}
    assert transport.requests == [HttpPostRequest("issue_tracker", "POST", POST_PATH, (), "status", b"null")]


def test_same_post_tool_runs_in_cpython_and_monty(sdk_mount: MountDir) -> None:
    namespace = run_path(str(CONNECTOR_FILE))
    manifest = namespace["connector"].manifest()
    tool = next(tool for tool in manifest["tools"] if tool["operation_name"] == "create_issue")
    reply = RawHttpResponse(status=201, body=b'{"id":7}')
    local_transport = RecordedTransport([reply])
    sandbox_transport = RecordedTransport([reply])

    async def verify() -> None:
        local = HttpRequestBoundary(targets=manifest["http_targets"], transport=local_transport, approved_post_paths=POST_APPROVAL)
        sandbox = HttpRequestBoundary(targets=manifest["http_targets"], transport=sandbox_transport, approved_post_paths=POST_APPROVAL)
        inputs = {"configuration": CONFIGURATION, "title": "Café"}
        local_context = HttpContext(dispatch=local.dispatch)
        local_result = await namespace["create_issue"](context=local_context, **inputs)
        local_invalid = await namespace["create_issue"](context=local_context, **(inputs | {"title": range(2)}))
        async with AsyncMonty() as pool, HttpInvocation(sandbox) as invocation:
            modules = {"http_binding": ExternalModule({"dispatch": invocation.dispatch})}
            async with pool.checkout(external_modules=modules) as session:
                await session.feed_run("import umbod_sdk.connectors.http", mount=sdk_mount, cwd="/sdk")
                await session.feed_run(CONNECTOR_FILE.read_text())
                sandbox_result = await session.feed_run(
                    "from http_binding import dispatch\n"
                    "context = HttpContext(dispatch=dispatch)\n"
                    "await connector._handler(handler_id)(configuration=configuration, context=context, title=title)",
                    inputs=inputs | {"handler_id": tool["handler_id"]},
                )
                sandbox_invalid = await session.feed_run(
                    "await connector._handler(handler_id)(configuration=configuration, context=context, title=range(2))",
                    inputs={"configuration": CONFIGURATION, "handler_id": tool["handler_id"]},
                )
        assert local_invalid == sandbox_invalid == {"error": "invalid_request"}
        assert local_result == sandbox_result == {"status": 201, "body": {"kind": "json", "value": {"id": 7}}}
        assert local_transport.requests == sandbox_transport.requests == [
            HttpPostRequest("issue_tracker", "POST", POST_PATH, (), "json", '{"title":"Café"}'.encode())
        ]

    asyncio.run(verify())


class GatedTransport:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.released = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.attempts = 0

    async def send(self, request: HttpRequest) -> RawHttpResponse:
        self.attempts += 1
        self.started.set()
        try:
            await self.released.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return RawHttpResponse(status=200, body=b'{"id": 5}')


@pytest.mark.parametrize("request_factory", [_request, _post_request])
def test_monty_invocation_cancels_its_host_request_without_cancelling_another(
    sdk_mount: MountDir, request_factory: Callable[[], dict[str, Any]]
) -> None:
    async def verify() -> None:
        cancelled_transport = GatedTransport()
        active_transport = GatedTransport()
        async with AsyncMonty(max_processes=2) as pool:
            async def invoke(transport: GatedTransport) -> dict[str, Any]:
                boundary = HttpRequestBoundary(targets=TARGETS, transport=transport, approved_post_paths=POST_APPROVAL)
                async with HttpInvocation(boundary) as invocation:
                    modules = {"http_binding": ExternalModule({"dispatch": invocation.dispatch})}
                    async with pool.checkout(external_modules=modules) as session:
                        await session.feed_run("import umbod_sdk.connectors.http", mount=sdk_mount, cwd="/sdk")
                        return await session.feed_run(
                            "from http_binding import dispatch\nawait dispatch(request)", inputs={"request": request_factory()}
                        )

            async with asyncio.timeout(8), asyncio.TaskGroup() as group:
                cancelled = group.create_task(invoke(cancelled_transport))
                active = group.create_task(invoke(active_transport))
                await cancelled_transport.started.wait()
                await active_transport.started.wait()
                cancelled.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await cancelled
                assert cancelled_transport.cancelled.is_set()
                assert cancelled_transport.attempts == 1
                assert not active.done()
                active_transport.released.set()
                assert await active == {"status": 200, "body": {"kind": "json", "value": {"id": 5}}}

    asyncio.run(verify())
