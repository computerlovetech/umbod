import asyncio
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Database,
    Field,
    InsertCommand,
    IntegerCodec,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
    TransactionMode,
)


class ApprovalNonceConsumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nonce: str
    expires_at: int


class ApprovalNonceConsumptionKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nonce: str


class ApprovalNonceStore(Protocol):
    async def consume(self, consumption: ApprovalNonceConsumption) -> bool: ...


class InMemoryApprovalNonceStore:
    def __init__(self) -> None:
        self._nonces: set[str] = set()
        self._lock = asyncio.Lock()

    async def consume(self, consumption: ApprovalNonceConsumption) -> bool:
        async with self._lock:
            if consumption.nonce in self._nonces:
                return False
            self._nonces.add(consumption.nonce)
            return True


_IDENTITY = TableIdentity("connector_approval_nonces")
_NONCE = Field[ApprovalNonceConsumption, str](_IDENTITY, "nonce", TextCodec())
_EXPIRES_AT = Field[ApprovalNonceConsumption, int](_IDENTITY, "expires_at", IntegerCodec())
APPROVAL_NONCE_TABLE = Table(
    _IDENTITY,
    RowCodec(
        ApprovalNonceConsumption,
        cast(tuple[Field[ApprovalNonceConsumption, object], ...], (_NONCE, _EXPIRES_AT)),
    ),
    KeyCodec(
        ApprovalNonceConsumptionKey,
        cast(tuple[Field[ApprovalNonceConsumption, object], ...], (_NONCE,)),
    ),
)


class DatabaseApprovalNonceStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def consume(self, consumption: ApprovalNonceConsumption) -> bool:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await session.insert(
                APPROVAL_NONCE_TABLE,
                InsertCommand(row=consumption),
            )


__all__ = [
    "APPROVAL_NONCE_TABLE",
    "ApprovalNonceConsumption",
    "ApprovalNonceStore",
    "DatabaseApprovalNonceStore",
    "InMemoryApprovalNonceStore",
]
