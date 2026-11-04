from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.filesystem import StorageKey


class MigrationStream(AsyncIterator[bytes], Protocol):
    async def aclose(self) -> None: ...


class MigrationKeys(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    keys: tuple[StorageKey, ...]


class Fingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MigrationSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    copied: int = Field(ge=0)
    skipped: int = Field(ge=0)
    planned: int = Field(ge=0)
    total_bytes: int = Field(ge=0)


class MigrationSource(Protocol):
    async def list_keys(self) -> MigrationKeys: ...
    def get(self, key: StorageKey) -> MigrationStream: ...


class MigrationTarget(Protocol):
    async def exists(self, key: StorageKey) -> bool: ...
    def get(self, key: StorageKey) -> MigrationStream: ...
    async def write_at(self, key: StorageKey, stream: MigrationStream) -> None: ...
