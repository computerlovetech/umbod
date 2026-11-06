import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from umbod.core.persistence import AllFields, NoFilter, OrderBy, Query
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.persistence_processes import claim_and_create_in_process
from tests.umbod.core.persistence.contract_support import row, table


@pytest.mark.asyncio
async def test_sqlite_serialized_processes_initialize_one_claim_and_preserve_all_inserts(tmp_path: Path) -> None:
    path = tmp_path / "processes.sqlite"
    contract_table, _, record, _ = table("process_claims")
    runtime = await prepared_sqlite_runtime(path)
    try:
        await runtime.database.ensure_schema((contract_table,))
    finally:
        await runtime.shutdown()
    names = tuple(f"child-{index}" for index in range(8))
    context = multiprocessing.get_context("spawn")
    loop = asyncio.get_running_loop()
    with context.Manager() as manager:
        gate = manager.Barrier(2)
        with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
            observations = await asyncio.gather(*(
                loop.run_in_executor(pool, claim_and_create_in_process, path, name, gate)
                for name in names
            ))
    claimants = {claimant for claimant, _, _, _ in observations}
    assert len(claimants) == 1
    assert claimants <= set(names)
    assert sum(initialized for _, initialized, _, _ in observations) == 1
    assert all(created for _, _, created, _ in observations)
    assert len({process_id for _, _, _, process_id in observations}) == 2
    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=False)
    async with reader.read_session() as session:
        stored = await session.find_many(contract_table, Query(NoFilter(), AllFields(), OrderBy((record,))))
    claimant, = claimants
    assert stored == tuple(row(name, f"created:{name}") for name in names) + (row("root", claimant),)
