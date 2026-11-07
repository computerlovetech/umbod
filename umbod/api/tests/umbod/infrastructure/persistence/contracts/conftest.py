from pathlib import Path
from typing import cast

import pytest

from umbod.core.persistence import Database
from tests.umbod.infrastructure.persistence.adapters import DATABASE_ADAPTERS, DatabaseAdapter


@pytest.fixture(params=DATABASE_ADAPTERS, ids=lambda adapter: cast(DatabaseAdapter, adapter).name)
def database(request: pytest.FixtureRequest) -> Database:
    adapter = cast(DatabaseAdapter, request.param)
    path = request.getfixturevalue("tmp_path") if adapter.name == "sqlite" else Path()
    return adapter.factory(path)
