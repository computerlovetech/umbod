from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from collections.abc import Awaitable


class HttpContext:
    def __init__(self, *, dispatch: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self._dispatch = dispatch

    async def request(
        self,
        target: str,
        *,
        path: list[str],
        query: list[list[str]],
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        request = _relative_request("GET", target, path, query)
        request["response_mode"] = "json"
        request["response_schema"] = response_schema
        return await self._dispatch(request)

    async def request_status(
        self,
        target: str,
        *,
        path: list[str],
        query: list[list[str]],
    ) -> dict[str, Any]:
        request = _relative_request("GET", target, path, query)
        request["response_mode"] = "status"
        return await self._dispatch(request)


    async def post(
        self,
        target: str,
        *,
        path: list[str],
        query: list[list[str]],
        json_body: object,
        request_schema: dict[str, Any],
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        request = _relative_post(target, path, query, json_body, request_schema)
        request["response_mode"] = "json"
        request["response_schema"] = response_schema
        return await self._dispatch_post(request)

    async def post_status(
        self,
        target: str,
        *,
        path: list[str],
        query: list[list[str]],
        json_body: object,
        request_schema: dict[str, Any],
    ) -> dict[str, Any]:
        request = _relative_post(target, path, query, json_body, request_schema)
        request["response_mode"] = "status"
        return await self._dispatch_post(request)

    async def _dispatch_post(self, request: dict[str, Any]) -> dict[str, Any]:
        if not _is_json(request):
            return {"error": "invalid_request"}
        return await self._dispatch(request)


def _relative_request(method: str, target: str, path: list[str], query: list[list[str]]) -> dict[str, Any]:
    return {"target": target, "method": method, "path": path, "query": query}


def _relative_post(
    target: str, path: list[str], query: list[list[str]], json_body: object, request_schema: dict[str, Any]
) -> dict[str, Any]:
    request = _relative_request("POST", target, path, query)
    request["json_body"] = json_body
    request["request_schema"] = request_schema
    return request


def _is_json(value: Any) -> bool:
    try:
        return _is_json_value(value)
    except RecursionError:
        return False


def _is_json_value(value: Any) -> bool:
    kind = type(value)
    if value is None or kind is bool or kind is int or kind is str:
        return True
    if kind is float:
        return -float("inf") < value < float("inf")
    if kind is list:
        for item in value:
            if not _is_json_value(item):
                return False
        return True
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str or not _is_json_value(item):
                return False
        return True
    return False
