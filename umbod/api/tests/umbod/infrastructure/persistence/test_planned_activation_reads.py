import sqlite3
from typing import cast
from unittest.mock import AsyncMock

import pytest

from umbod.core.activation.stores.reads import plan_activation_reads
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.persistence import DatabaseSession, ReadPlan, ReadPlanOperations
from umbod.infrastructure.persistence.sqlite.compiler import SQLiteCompiler
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper


@pytest.mark.asyncio
async def test_activation_batch_uses_compound_primary_key_without_table_scan() -> None:
    session = AsyncMock(spec=DatabaseSession)
    session.find_many.return_value = ()
    plan: ReadPlanOperations = ReadPlan()
    plan_activation_reads(plan, ("target", "other"))
    await plan.execute(cast(DatabaseSession, session))
    table, query = session.find_many.call_args.args
    compiler = SQLiteCompiler(SQLiteValueMapper())
    schema = compiler.create_table(CAPABILITY_ACTIVATION_STATE_TABLE)
    select = compiler.select(table, query, limit_one=False)
    with sqlite3.connect(":memory:") as connection:
        connection.execute(schema.statement, schema.parameters)
        explanation = connection.execute(
            "EXPLAIN QUERY PLAN " + select.statement, select.parameters,
        ).fetchall()
    assert any("SEARCH capability_activation_states USING INDEX" in row[3] for row in explanation)
    assert not any("SCAN capability_activation_states" in row[3] for row in explanation)
