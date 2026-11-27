from asyncio import Task, TaskGroup
from types import TracebackType
from typing import Any, Self, Unpack

from umbod_sdk.connectors.api.http import HttpRequestBoundary


type _ExitArguments = tuple[type[BaseException] | None, BaseException | None, TracebackType | None]


class HttpInvocation:
    def __init__(self, boundary: HttpRequestBoundary) -> None:
        self._boundary = boundary
        self._tasks: set[Task[dict[str, Any]]] = set()
        self._group = TaskGroup()
        self._open = False

    async def __aenter__(self) -> Self:
        await self._group.__aenter__()
        self._open = True
        return self

    async def __aexit__(self, *exit_arguments: Unpack[_ExitArguments]) -> None:
        self._open = False
        for task in self._tasks:
            task.cancel()
        await self._group.__aexit__(*exit_arguments)

    async def dispatch(self, request: object) -> dict[str, Any]:
        if not self._open:
            return {"error": "invocation_closed"}
        task = self._group.create_task(self._boundary.dispatch(request))
        self._tasks.add(task)
        try:
            return await task
        finally:
            self._tasks.discard(task)
