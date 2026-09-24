import re
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter


PublicToolName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]+$")]
ToolNamePrefix = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$")]
_PUBLIC_TOOL_NAME_ADAPTER = TypeAdapter(PublicToolName)
_TOOL_NAME_PREFIX_ADAPTER = TypeAdapter(ToolNamePrefix)


class PublicToolIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector_id: str
    tool_name_prefix: str
    operation_name: str


class PublicToolIdentitySource(Protocol):
    async def identities(self) -> tuple[PublicToolIdentity, ...]: ...


class PublicToolNameConflictError(ValueError):
    def __init__(
        self,
        public_name: str,
        first: PublicToolIdentity,
        second: PublicToolIdentity,
    ) -> None:
        self.public_name = public_name
        self.first = first
        self.second = second
        super().__init__(f"Public tool name '{public_name}' is ambiguous")


def normalize_tool_name_prefix(display_name: str) -> str:
    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", display_name).strip("_")
    return prefix or "connector"


def mangle_public_tool_name(tool_name_prefix: str, operation_name: str) -> str:
    tool_name = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{tool_name_prefix}_{operation_name}").strip("_")
    return _PUBLIC_TOOL_NAME_ADAPTER.validate_python(tool_name)


class PublicToolNameValidator:
    def validate_prefix(self, tool_name_prefix: str) -> str:
        return _TOOL_NAME_PREFIX_ADAPTER.validate_python(tool_name_prefix)

    def validate_unique(self, identities: tuple[PublicToolIdentity, ...]) -> None:
        by_name: dict[str, PublicToolIdentity] = {}
        for identity in identities:
            self.validate_prefix(identity.tool_name_prefix)
            public_name = mangle_public_tool_name(
                identity.tool_name_prefix, identity.operation_name
            )
            existing = by_name.get(public_name)
            if existing is not None:
                raise PublicToolNameConflictError(public_name, existing, identity)
            by_name[public_name] = identity


def validate_unique_public_tool_names(identities: tuple[PublicToolIdentity, ...]) -> None:
    PublicToolNameValidator().validate_unique(identities)
