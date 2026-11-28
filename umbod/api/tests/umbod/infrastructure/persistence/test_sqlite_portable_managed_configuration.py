from pathlib import Path
from uuid import uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.connectors.portable.drafts import DraftReceipt
from umbod.core.connectors.portable.managed import DatabaseManagedConnectorStore
from umbod.core.connectors.portable.managed.catalog import PortableConnectorCatalog
from umbod.core.connectors.portable.managed.catalog_models import (
    SavedConfiguration,
    UnsavedConfiguration,
)
from umbod.core.connectors.portable.managed.catalog_store import (
    DatabaseManagedConnectorCatalogStore,
)
from umbod.core.connectors.portable.managed.models import (
    InactiveConnectorSnapshot,
    PortableConnectorSubmission,
)
from umbod.core.connectors.portable.managed.schema import MANAGED_CONNECTOR_TABLE
from umbod.infrastructure.connections import UnpooledConnectionProvider
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


@pytest.mark.asyncio
async def test_pre_configuration_database_keeps_submissions_and_new_values_after_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "portable.sqlite"
    driver = SQLiteConnectionDriver(str(path), create_parent_dirs=True)
    previous_database = SQLiteDatabase(
        UnpooledConnectionProvider(driver.connect, driver.close)
    )
    submission = PortableConnectorSubmission(
        revision=DraftReceipt(uuid4(), uuid4(), "a" * 64),
        profile_id="validation-profile",
        snapshot=InactiveConnectorSnapshot(
            declared_connector_id="probe",
            display_name="Probe",
            description="Inactive probe",
            configuration_schema_json=(
                '{"additionalProperties":false,"properties":{"workspace":{"type":"string","minLength":1},'
                '"alias":{"type":"string"}},"required":["workspace"],"type":"object"}'
            ),
        ),
    )
    await previous_database.ensure_schema((MANAGED_CONNECTOR_TABLE,))
    receipt = await DatabaseManagedConnectorStore(previous_database).submit(submission)

    upgraded = await prepared_sqlite_runtime(path)
    connector_id = receipt.connector_id
    try:
        catalog = PortableConnectorCatalog(
            DatabaseManagedConnectorCatalogStore(upgraded.database)
        )
        original = await catalog.read_configuration(connector_id)
        assert original.configuration is UnsavedConfiguration.NOT_SAVED
        assert await catalog.list_connectors() == (original.connector,)

        first = await catalog.replace_configuration(
            original, {"workspace": "demo", "alias": "old"}
        )
        latest = await catalog.replace_configuration(first, {"workspace": "reviewed"})
        resubmitted = await DatabaseManagedConnectorStore(upgraded.database).submit(
            submission
        )

        assert resubmitted == receipt
        assert latest.configuration == SavedConfiguration({"workspace": "reviewed"})
    finally:
        await upgraded.shutdown()

    reopened = await prepared_sqlite_runtime(path)
    try:
        catalog = PortableConnectorCatalog(
            DatabaseManagedConnectorCatalogStore(reopened.database)
        )
        loaded = await catalog.read_configuration(connector_id)
        assert loaded == latest
        assert loaded.fields == original.fields
        assert loaded.connector.configured
        assert loaded.connector.status == "inactive"
        assert await catalog.list_connectors() == (loaded.connector,)
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_empty_configuration_is_configured_when_schema_has_no_required_fields(
    tmp_path: Path,
) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "portable.sqlite")
    try:
        receipt = await DatabaseManagedConnectorStore(runtime.database).submit(
            PortableConnectorSubmission(
                revision=DraftReceipt(uuid4(), uuid4(), "a" * 64),
                profile_id="validation-profile",
                snapshot=InactiveConnectorSnapshot(
                    declared_connector_id="empty_probe",
                    display_name="Empty probe",
                    description="Inactive probe",
                    configuration_schema_json='{"additionalProperties":false,"properties":{},"type":"object"}',
                ),
            )
        )
        catalog = PortableConnectorCatalog(
            DatabaseManagedConnectorCatalogStore(runtime.database)
        )
        original = await catalog.read_configuration(receipt.connector_id)
        await catalog.replace_configuration(original, {})

        configured = await catalog.read_configuration(receipt.connector_id)
        assert configured.configuration == SavedConfiguration({})
        assert configured.connector.configured is True
        assert await catalog.list_connectors() == (configured.connector,)
    finally:
        await runtime.shutdown()
