from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.resources.base import ResourceResult


class OwnershipCheckedResource(Resource):
    _backend: Resource
    _ensure_access: Callable[[], Awaitable[None]]

    def __init__(
        self, backend: Resource, ensure_access: Callable[[], Awaitable[None]]
    ) -> None:
        super().__init__(**backend.model_dump())
        self._backend = backend
        self._ensure_access = ensure_access

    async def read(self) -> ResourceResult:
        await self._ensure_access()
        return await self._backend.read()


class OwnershipCheckedTemplate(ResourceTemplate):
    _backend: ResourceTemplate
    _ensure_access: Callable[[], Awaitable[None]]

    def __init__(
        self, backend: ResourceTemplate, ensure_access: Callable[[], Awaitable[None]]
    ) -> None:
        super().__init__(**backend.model_dump())
        self._backend = backend
        self._ensure_access = ensure_access

    async def create_resource(self, uri: str, params: dict[str, Any]) -> Resource:
        await self._ensure_access()
        resource = await self._backend.create_resource(uri, params)
        return OwnershipCheckedResource(resource, self._ensure_access)
