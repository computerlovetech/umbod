from collections.abc import Sequence
from typing import Protocol
from contextlib import AbstractAsyncContextManager

from fastmcp.exceptions import ToolError

from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinitionModel, uses_personal_oauth


class PersonalToolNameMatcher(Protocol):
    def is_personal_tool_name(self, name: str) -> bool: ...


class PersonalToolNamespace(Protocol):
    def discovery_operation(self) -> AbstractAsyncContextManager[object]: ...

    async def capture_personal_tool_namespace(self) -> PersonalToolNameMatcher: ...

    async def is_personal_tool_name(self, name: str) -> bool: ...


class PersonalToolNamespaceSnapshot:
    def __init__(self, definitions: Sequence[ConnectorDefinitionModel], scope: str) -> None:
        sentinel = "UmbodPersonalNamespaceSentinel"
        self._stems = tuple(
            mangle_public_tool_name(definition.tool_name_prefix, sentinel).removesuffix(sentinel)
            for definition in definitions
            if uses_personal_oauth(definition) and (not scope or definition.connector_id == scope)
        )
        self._scoped = bool(scope)

    def is_personal_tool_name(self, name: str) -> bool:
        if any(not stem for stem in self._stems):
            raise ToolError("public_tool_name_conflict")
        owners = sum(self._scoped or name == stem.rstrip("_") or name.startswith(stem) for stem in self._stems)
        if owners > 1:
            raise ToolError("public_tool_name_conflict")
        return bool(owners)
