import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.fixture
def prepared_connector_store_database(
    isolated_connector_store_database: Path,
) -> Generator[Path, None, None]:
    runtime = asyncio.run(prepared_sqlite_runtime(isolated_connector_store_database))
    try:
        yield isolated_connector_store_database
    finally:
        asyncio.run(runtime.shutdown())
