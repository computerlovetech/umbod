import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from umbod.core.filesystem.errors import PolicyDecodingFailure
from umbod.core.filesystem.models import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.filesystem.stores.schema import GRANT_NODE, GRANT_TABLE, GrantRecord
from umbod.core.persistence import AllFields, Equals, InsertCommand, PersistenceDecodingError, Query, TransactionMode, Unordered
from umbod.infrastructure.persistence.schema_preparation import prepare_application_schema
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


@pytest.mark.parametrize("corruption", ["invalid-json", "invalid-permissions"])
@pytest.mark.asyncio
async def test_sqlite_corrupt_grant_reports_decoding_context_and_policy_failure(
    tmp_path: Path, corruption: str,
) -> None:
    path = tmp_path / "policy.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await prepare_application_schema(database)
    grant = AccessGrant(
        node_id=uuid4(),
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.WRITE},
        recursive=False,
    )
    record = GrantRecord(
        node_id=str(grant.node_id), principal_type=grant.principal.type.value,
        issuer=grant.principal.issuer, principal_id=grant.principal.id, payload=grant,
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.insert(GRANT_TABLE, InsertCommand(row=record))
    payload = "{" if corruption == "invalid-json" else json.dumps({
        **grant.model_dump(mode="json"), "permissions": ["bogus"],
    })
    with closing(sqlite3.connect(path)) as connection:
        changed = connection.execute(
            "UPDATE filesystem_grants SET payload = ? WHERE node_id = ?",
            (payload, str(grant.node_id)),
        )
        assert changed.rowcount == 1
        connection.commit()
    async with database.read_session() as session:
        with pytest.raises(PersistenceDecodingError) as decoded:
            await session.find_many(
                GRANT_TABLE, Query(Equals(GRANT_NODE, str(grant.node_id)), AllFields(), Unordered()),
            )
        assert decoded.value.table_name == GRANT_TABLE.identity.name
        assert decoded.value.field_name == "payload"
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(PolicyDecodingFailure) as translated:
            await SessionAccessControl(session).list_grants(grant.node_id)
        assert isinstance(translated.value.__cause__, PersistenceDecodingError)
        assert translated.value.__cause__.table_name == GRANT_TABLE.identity.name
        assert translated.value.__cause__.field_name == "payload"
