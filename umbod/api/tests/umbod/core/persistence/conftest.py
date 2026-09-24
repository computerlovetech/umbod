from pathlib import Path
from typing import cast

import pytest

from umbod.core.persistence import Database
from tests.umbod.core.persistence.contract_support import DATABASE_ADAPTERS, DatabaseAdapter


@pytest.fixture(params=DATABASE_ADAPTERS, ids=lambda adapter: cast(DatabaseAdapter, adapter).name)
def database(request: pytest.FixtureRequest, tmp_path: Path) -> Database:
    adapter = cast(DatabaseAdapter, request.param)
    return adapter.factory(tmp_path)
