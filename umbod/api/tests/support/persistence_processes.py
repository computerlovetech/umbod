import asyncio
import os
from pathlib import Path
from typing import Protocol

from umbod.core.persistence import AllFields, Equals, InsertCommand, Query, TransactionMode, Unordered
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.persistence_contracts import row, table


class ProcessStartGate(Protocol):
    def wait(self, timeout: float) -> int: ...


async def _claim_and_create(database_path: Path, name: str) -> tuple[str, bool, bool, int]:
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        contract_table, _, record, _ = table("process_claims")
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            existing = await session.find_one(
                contract_table, Query(Equals(record, "root"), AllFields(), Unordered()),
            )
            if existing is None:
                claimant = name
                initialized = await session.insert(contract_table, InsertCommand(row=row("root", claimant)))
            else:
                claimant = existing.payload
                initialized = False
            created = await session.insert(contract_table, InsertCommand(row=row(name, f"created:{name}")))
        return claimant, initialized, created, os.getpid()
    finally:
        await runtime.shutdown()


def claim_and_create_in_process(
    database_path: Path, name: str, gate: ProcessStartGate,
) -> tuple[str, bool, bool, int]:
    gate.wait(timeout=15)
    return asyncio.run(_claim_and_create(database_path, name))
