from pathlib import Path

from umbod.core.persistence import Database
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


def create_contract_sqlite_database(directory: Path) -> Database:
    return create_unpooled_sqlite_database(str(directory / "contract.sqlite"), create_parent_dirs=True)
