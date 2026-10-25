import pytest

from tests.support.virtual_filesystem import (
    FilesystemAcceptanceContext,
    create_acceptance_context,
)


@pytest.fixture
def filesystem_context() -> FilesystemAcceptanceContext:
    return create_acceptance_context()
