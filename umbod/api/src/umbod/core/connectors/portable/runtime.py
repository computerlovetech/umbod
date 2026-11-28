from asyncio import get_running_loop, timeout_at
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from hashlib import sha256
from math import isfinite

from pydantic import JsonValue
from umbod_sdk.connectors.api.http import HttpRequestBoundary, HttpTransport
from umbod_sdk.connectors.api.http_scope import HttpInvocation

from .contracts import PortableExecutionLimits, PortableHttpAccess, PreparedPortableConnector
from .ports import HttpDispatch, PortableExecutionError, PortableSandbox
from .validation import (
    check_manifest_handlers,
    checked_result,
    enforce_schema,
    json_snapshot,
    read_manifest,
    snapshot_object,
    tool_for,
)


class PortableConnectorRuntime:
    def __init__(self, sandbox: PortableSandbox, transport: HttpTransport, limits: PortableExecutionLimits) -> None:
        if not isfinite(limits.deadline_seconds) or limits.deadline_seconds <= 0 or limits.max_http_calls < 0:
            raise ValueError("Invalid portable execution limits")
        self._sandbox = sandbox
        self._transport = transport
        self._limits = limits

    async def prepare(self, source: str) -> PreparedPortableConnector:
        async with self._deadline():
            async with self._sandbox.open(source, _closed_dispatch) as session:
                manifest = read_manifest(await session.manifest())
                check_manifest_handlers(manifest)
            return PreparedPortableConnector(source, _source_digest(source), json_snapshot(manifest))

    async def check_configuration(
        self, connector: PreparedPortableConnector, configuration: dict[str, JsonValue], access: PortableHttpAccess
    ) -> bool:
        async with self._deadline() as check_deadline:
            manifest = connector.manifest
            configuration = _checked_configuration(connector, configuration)
            value = await self._invoke(
                connector,
                manifest["configuration_check_handler_id"],
                {"configuration": configuration},
                PortableHttpAccess(access.approved_targets, frozenset()),
                check_deadline,
            )
            if not isinstance(value, bool):
                raise PortableExecutionError("Invalid portable configuration check result")
            return value

    async def invoke_tool(
        self,
        connector: PreparedPortableConnector,
        operation: str,
        configuration: dict[str, JsonValue],
        arguments: dict[str, JsonValue],
        access: PortableHttpAccess,
    ) -> JsonValue:
        async with self._deadline() as check_deadline:
            manifest = connector.manifest
            tool = tool_for(manifest, operation)
            configuration = _checked_configuration(connector, configuration)
            arguments = snapshot_object(arguments, "Invalid portable tool arguments")
            reserved = {"configuration", "context"} if manifest["manifest_version"] == 2 else {"configuration"}
            if reserved.intersection(arguments):
                raise PortableExecutionError("Invalid portable tool arguments")
            enforce_schema(tool["input_schema"], arguments, "Invalid portable tool arguments")
            value = checked_result(await self._invoke(
                connector, tool["handler_id"], {**arguments, "configuration": configuration}, access, check_deadline
            ))
            if "output_schema" in tool:
                enforce_schema(tool["output_schema"], value, "Invalid portable tool output")
            return value

    async def _invoke(
        self,
        connector: PreparedPortableConnector,
        handler_id: str,
        arguments: dict[str, JsonValue],
        access: PortableHttpAccess,
        check_deadline: Callable[[], None],
    ) -> object:
        if _source_digest(connector.source) != connector._source_digest:
            raise PortableExecutionError("Portable connector source changed after preparation")
        check_deadline()
        manifest = connector.manifest
        active_dispatch: HttpDispatch = _closed_dispatch

        async def dispatch(request: object) -> dict[str, object]:
            return await active_dispatch(request)

        async with self._sandbox.open(connector.source, dispatch) as session:
            if json_snapshot(read_manifest(await session.manifest())) != json_snapshot(manifest):
                raise PortableExecutionError("Portable connector manifest changed after preparation")
            check_deadline()
            if manifest["manifest_version"] == 1:
                return await session.run(handler_id, arguments, use_http=False)
            async with self._http_scope(manifest["http_targets"], access) as invocation_dispatch:
                active_dispatch = invocation_dispatch
                try:
                    return await session.run(handler_id, arguments, use_http=True)
                finally:
                    active_dispatch = _closed_dispatch

    @asynccontextmanager
    async def _http_scope(self, declarations: dict[str, str], access: PortableHttpAccess) -> AsyncIterator[HttpDispatch]:
        boundary = HttpRequestBoundary(
            targets={target: description for target, description in declarations.items() if target in access.approved_targets},
            transport=self._transport,
            approved_post_paths=tuple(access.approved_post_paths),
        )
        async with HttpInvocation(boundary) as invocation:
            remaining_calls = self._limits.max_http_calls

            async def dispatch(request: object) -> dict[str, object]:
                nonlocal remaining_calls
                if remaining_calls == 0:
                    return {"error": "limit_exceeded"}
                remaining_calls -= 1
                return await invocation.dispatch(request)

            yield dispatch

    @asynccontextmanager
    async def _deadline(self) -> AsyncIterator[Callable[[], None]]:
        clock = get_running_loop().time
        expires_at = clock() + self._limits.deadline_seconds

        def check_deadline() -> None:
            if clock() >= expires_at:
                raise TimeoutError

        try:
            async with timeout_at(expires_at):
                yield check_deadline
                check_deadline()
        except TimeoutError:
            raise PortableExecutionError("Portable connector execution timed out") from None


def _source_digest(source: str) -> bytes:
    return sha256(source.encode("utf-8")).digest()


def _checked_configuration(
    connector: PreparedPortableConnector, configuration: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    configuration = snapshot_object(configuration, "Invalid portable configuration")
    enforce_schema(connector.manifest["configuration_schema"], configuration, "Invalid portable configuration")
    return configuration


async def _closed_dispatch(_request: object) -> dict[str, object]:
    return {"error": "invocation_closed"}
