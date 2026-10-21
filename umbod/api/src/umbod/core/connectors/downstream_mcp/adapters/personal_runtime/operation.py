import json
from collections.abc import Callable
from datetime import datetime
from typing import NoReturn

import anyio
import httpx2

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall


class OperationState:
    def __init__(self, target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, clock: Callable[[], datetime], scope: anyio.CancelScope, operation: PersonalRuntimeTarget | PersonalToolCall) -> None:
        self.target = target
        self.limits = limits
        self.clock = clock
        self.scope = scope
        self.operation = operation
        self.deadline = min(scope.deadline, anyio.current_time() + min(limits.operation_timeout_seconds, (target.expires_at - clock()).total_seconds() - 0.1))
        self.failed = False
        self.authorization_rejected = False
        self.cleaning_up = False
        self.total_bytes = 0
        self.initialized = False
        self.notifications = 0
        self.gets = 0
        self.deletes = 0
        self.calls = 0
        self.cursors: set[str] = set()
        self.expected_cursor = ""
        self.pages = 0
        self.preflight_complete = False
        self.url = httpx2.URL(target.endpoint_url)
        if self.url.scheme != "https" or not self.url.host or self.url.userinfo or self.url.fragment or "#" in target.endpoint_url:
            self.fail()

    def fail(self) -> NoReturn:
        if not self.cleaning_up:
            self.failed = True
            self.scope.cancel()
        raise PersonalRuntimeUnavailable("Personal MCP unavailable") from None

    def check(self) -> None:
        if self.failed or self.clock() >= self.target.expires_at or anyio.current_time() >= self.deadline:
            self.fail()

    def account(self, size: int, response_bytes: int) -> None:
        self.check()
        self.total_bytes += size
        if response_bytes > self.limits.maximum_response_bytes or self.total_bytes > self.limits.maximum_total_bytes:
            self.fail()

    def authorize(self, request: httpx2.Request, body: bytes) -> None:
        self.check()
        if (
            request.url != self.url or "last-event-id" in request.headers
            or "sni_hostname" in request.extensions
            or request.headers.get("authorization") != f"Bearer {self.target.access_token.get_secret_value()}"
            or request.headers.get("host") != self.url.netloc.decode("ascii")
            or len(body) > self.limits.maximum_request_bytes
        ):
            self.fail()
        if request.method in {"GET", "DELETE"}:
            self._authorize_stream_control(request.method, body)
        elif request.method == "POST":
            self._authorize_message(body)
        else:
            self.fail()

    def _authorize_stream_control(self, method: str, body: bytes) -> None:
        if not self.initialized or body:
            self.fail()
        if method == "GET":
            self.gets += 1
            if self.gets > 1:
                self.fail()
        else:
            self.deletes += 1
            if self.deletes > 1:
                self.fail()

    def _authorize_message(self, body: bytes) -> None:
        try:
            message = json.loads(body)
        except (ValueError, UnicodeError):
            self.fail()
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or set(message) - {"jsonrpc", "id", "method", "params"}:
            self.fail()
        params = message.get("params", {})
        if not isinstance(params, dict) or ("_meta" in params and params["_meta"] != {}):
            self.fail()
        params = {key: value for key, value in params.items() if key != "_meta"}
        handlers = {"initialize": self._initialize, "notifications/initialized": self._notification, "tools/list": self._list, "tools/call": self._call}
        handler = handlers.get(message.get("method"))
        if handler is None:
            self.fail()
        handler(message, params)

    def _initialize(self, message: dict[str, object], params: dict[str, object]) -> None:
        if self.initialized or "id" not in message or set(params) - {"protocolVersion", "capabilities", "clientInfo"}:
            self.fail()
        self.initialized = True

    def _notification(self, message: dict[str, object], params: dict[str, object]) -> None:
        self.notifications += 1
        if not self.initialized or self.notifications > 1 or params or "id" in message:
            self.fail()

    def _list(self, message: dict[str, object], params: dict[str, object]) -> None:
        if not self.initialized or "id" not in message or self.notifications != 1 or self.calls or self.preflight_complete:
            self.fail()
        self.pages += 1
        cursor = params.get("cursor", "")
        if set(params) - {"cursor"} or not isinstance(cursor, str) or cursor != self.expected_cursor or cursor in self.cursors or self.pages > self.limits.maximum_tool_pages:
            self.fail()
        self.cursors.add(cursor)

    def _call(self, message: dict[str, object], params: dict[str, object]) -> None:
        if not self.initialized or not isinstance(self.operation, PersonalToolCall) or not self.preflight_complete or self.notifications != 1 or "id" not in message:
            self.fail()
        self.calls += 1
        if self.calls > 1 or params != {"name": self.operation.tool_name, "arguments": self.operation.arguments}:
            self.fail()
