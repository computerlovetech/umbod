from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from umbod.core.capabilities.descriptions.domain import CapabilityDescription

ConnectorKind = Literal["native", "downstream_mcp", "openapi"]
ConnectorId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class OverrideRevisionConflictError(RuntimeError):
    pass


class ConnectorKindMismatchError(RuntimeError):
    pass


class CapabilityDescriptionTargetNotFoundError(LookupError):
    pass


class CapabilityDescriptionOverrideCorruptionError(RuntimeError):
    pass


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectorCapabilityDescriptionKey(DomainModel):
    kind: ConnectorKind
    connector_id: ConnectorId


class SetCapabilityDescriptionOverride(DomainModel):
    operation: Literal["set"] = "set"
    key: ConnectorCapabilityDescriptionKey
    description: CapabilityDescription
    expected_revision: Annotated[int, Field(ge=0)]


class ClearCapabilityDescriptionOverride(DomainModel):
    operation: Literal["clear"] = "clear"
    key: ConnectorCapabilityDescriptionKey
    expected_revision: Annotated[int, Field(ge=0)]


class SystemCapabilityDescription(DomainModel):
    state: Literal["system"] = "system"
    key: ConnectorCapabilityDescriptionKey
    revision: Annotated[int, Field(ge=0)]


class OverriddenCapabilityDescription(DomainModel):
    state: Literal["overridden"] = "overridden"
    key: ConnectorCapabilityDescriptionKey
    description: CapabilityDescription
    revision: Annotated[int, Field(ge=1)]


CapabilityDescriptionOverrideState: TypeAlias = Annotated[
    SystemCapabilityDescription | OverriddenCapabilityDescription,
    Field(discriminator="state"),
]


class EffectiveCapabilityDescription(DomainModel):
    key: ConnectorCapabilityDescriptionKey
    description: CapabilityDescription
    source: Literal["system", "override"]
    revision: Annotated[int, Field(ge=0)]


class ConnectorCapabilityDescriptionOverrideStore(Protocol):
    async def get(
        self, key: ConnectorCapabilityDescriptionKey
    ) -> CapabilityDescriptionOverrideState: ...
    async def get_many(
        self, keys: tuple[ConnectorCapabilityDescriptionKey, ...]
    ) -> tuple[CapabilityDescriptionOverrideState, ...]: ...
    async def set(
        self, command: SetCapabilityDescriptionOverride
    ) -> OverriddenCapabilityDescription: ...
    async def clear(
        self, command: ClearCapabilityDescriptionOverride
    ) -> SystemCapabilityDescription: ...
    async def delete(self, key: ConnectorCapabilityDescriptionKey) -> None: ...


class ConnectorCapabilityBaseDescriptionReader(Protocol):
    async def read(self, key: ConnectorCapabilityDescriptionKey) -> CapabilityDescription: ...


class SystemConnectorCapabilityDescriptionOverrideStore:
    async def get(
        self, key: ConnectorCapabilityDescriptionKey
    ) -> CapabilityDescriptionOverrideState:
        return SystemCapabilityDescription(key=key, revision=0)

    async def get_many(
        self, keys: tuple[ConnectorCapabilityDescriptionKey, ...]
    ) -> tuple[CapabilityDescriptionOverrideState, ...]:
        return tuple(SystemCapabilityDescription(key=key, revision=0) for key in keys)

    async def set(
        self, command: SetCapabilityDescriptionOverride
    ) -> OverriddenCapabilityDescription:
        raise RuntimeError("Capability description overrides are unavailable")

    async def clear(
        self, command: ClearCapabilityDescriptionOverride
    ) -> SystemCapabilityDescription:
        raise RuntimeError("Capability description overrides are unavailable")

    async def delete(self, key: ConnectorCapabilityDescriptionKey) -> None:
        raise RuntimeError("Capability description overrides are unavailable")


class CapabilityDescriptionOverrideResolver:
    def __init__(
        self,
        store: ConnectorCapabilityDescriptionOverrideStore,
        base_reader: ConnectorCapabilityBaseDescriptionReader,
    ) -> None:
        self._store = store
        self._base_reader = base_reader

    async def base_description(
        self, key: ConnectorCapabilityDescriptionKey
    ) -> CapabilityDescription:
        return await self._base_reader.read(key)

    async def resolve(
        self, key: ConnectorCapabilityDescriptionKey
    ) -> EffectiveCapabilityDescription:
        state = await self._store.get(key)
        if isinstance(state, OverriddenCapabilityDescription):
            return EffectiveCapabilityDescription(
                key=key, description=state.description, source="override", revision=state.revision
            )
        return EffectiveCapabilityDescription(
            key=key,
            description=await self._base_reader.read(key),
            source="system",
            revision=state.revision,
        )

    async def set(
        self, command: SetCapabilityDescriptionOverride
    ) -> EffectiveCapabilityDescription:
        await self._base_reader.read(command.key)
        state = await self._store.set(command)
        return EffectiveCapabilityDescription(
            key=command.key,
            description=state.description,
            source="override",
            revision=state.revision,
        )

    async def clear(
        self, command: ClearCapabilityDescriptionOverride
    ) -> EffectiveCapabilityDescription:
        description = await self._base_reader.read(command.key)
        state = await self._store.clear(command)
        return EffectiveCapabilityDescription(
            key=command.key, description=description, source="system", revision=state.revision
        )
