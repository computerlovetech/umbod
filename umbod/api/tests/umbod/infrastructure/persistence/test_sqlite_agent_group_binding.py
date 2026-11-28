from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.administrator import AdministratorAccess
from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.agent_tokens import (
    CreateAgent,
    InvalidAgentCredential,
    create_agent_credential_service,
    create_agent_credential_verifier,
)
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores import registration
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.reads import DatabaseGroupInstanceLookup


@pytest.mark.asyncio
async def test_recreated_group_from_another_runtime_does_not_revive_a_persisted_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "agent-group-binding.sqlite3"
    request = RegisterGroup(group_id="agent-group")
    administrator = AdministratorPrincipal(memberships=("administrators",))
    issuer = await prepared_sqlite_runtime(path)
    try:
        await create_group_management(issuer.database).register_group(request)
        management = create_agent_credential_service(
            issuer.database, AdministratorAccess("administrators")
        )
        issued = await management.create(
            administrator,
            CreateAgent(
                display_name="Build agent",
                group_id=request.group_id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            ),
        )
    finally:
        await issuer.shutdown()

    verifier = await prepared_sqlite_runtime(path)
    try:
        credentials = create_agent_credential_verifier(verifier.database)
        original = await credentials.verify_for_public_mcp(issued.token)
        assert original.agent_id == issued.metadata.agent_id
        remover = await prepared_sqlite_runtime(path)
        try:
            await create_group_management(remover.database).delete_group(
                request.group_id
            )
        finally:
            await remover.shutdown()

        writer = await prepared_sqlite_runtime(path)
        try:
            replacement_id = uuid4()
            candidates = iter((UUID(hex=original.group_instance_id), replacement_id))
            monkeypatch.setattr(registration, "uuid4", candidates.__next__)
            await create_group_management(writer.database).register_group(request)
            replacement = await DatabaseGroupInstanceLookup(
                writer.database
            ).find_group_instance(request.group_id)
            assert (
                replacement is not None
                and replacement.instance_id == replacement_id.hex
            )
        finally:
            await writer.shutdown()

        with pytest.raises(InvalidAgentCredential):
            await credentials.verify_for_public_mcp(issued.token)
    finally:
        await verifier.shutdown()
