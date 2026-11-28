from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import UUID

import pytest
from pydantic import ValidationError

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.administrator.operations import (
    AdministratorAccess,
    AdministratorAccessDenied,
)
from umbod.core.agent_tokens import (
    AgentCredentialConflict,
    AgentCredentialService,
    AgentCredentialStatus,
    AgentGroupNotFound,
    CreateAgent,
    InvalidAgentCredential,
    IssuedAgentCredential,
    RotateAgentCredential,
    SecureAgentCredentialGenerator,
)
from umbod.core.agent_tokens.schema import AGENT_METADATA
from umbod.core.agent_tokens.store import DatabaseAgentCredentialStore
from umbod.core.groups import GroupManagementService, RegisterGroup

from .conftest import MutableClock, MutableGroups

pytestmark = pytest.mark.asyncio


async def test_creation_issues_unique_agent_and_credential_ids(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
    issued: IssuedAgentCredential,
) -> None:
    other = await service.create(administrator, create_request)
    ids = {
        entry
        for result in (issued, other)
        for entry in (result.metadata.agent_id, result.metadata.credential_id)
    }
    assert len(ids) == 4
    assert all(UUID(hex=entry).hex == entry for entry in ids)
    assert issued.metadata.display_name == create_request.display_name
    assert issued.metadata.group_id == create_request.group_id
    assert issued.metadata.expires_at == create_request.expires_at
    assert issued.metadata.status is AgentCredentialStatus.ACTIVE


async def test_only_issuance_result_carries_the_bearer_and_only_storage_carries_its_digest(
    service: AgentCredentialService,
    store: DatabaseAgentCredentialStore,
    administrator: AdministratorPrincipal,
    issued: IssuedAgentCredential,
) -> None:
    bearer = issued.token.get_secret_value()
    stored = await store.find(issued.metadata.agent_id)
    assert stored is not None
    assert set(type(stored).model_fields) == {"metadata", "group_instance_id", "digest"}
    assert stored.digest == sha256(bearer.encode("ascii")).hexdigest()
    listed = await service.list_agents(administrator)
    assert listed == (issued.metadata,)
    for model in (issued, stored, *listed):
        assert "token" not in model.model_dump()
        assert "digest" not in model.model_dump()
        assert bearer not in repr(model)
        assert stored.digest not in repr(model)


async def test_listing_reports_expired_status_at_the_exact_expiry(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    clock: MutableClock,
    issued: IssuedAgentCredential,
) -> None:
    expiry = issued.metadata.expires_at
    assert isinstance(expiry, datetime)
    clock.instant = expiry

    assert await service.list_agents(administrator) == (
        issued.metadata.model_copy(update={"status": AgentCredentialStatus.EXPIRED}),
    )


async def test_non_expiring_credentials_stay_active_and_store_json_null(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    clock: MutableClock,
    non_expiring: IssuedAgentCredential,
) -> None:
    clock.instant += timedelta(days=36500)

    assert await service.list_agents(administrator) == (non_expiring.metadata,)
    assert non_expiring.metadata.status is AgentCredentialStatus.ACTIVE
    encoded = AGENT_METADATA.codec.encode(non_expiring.metadata)
    assert isinstance(encoded, dict)
    assert encoded["expires_at"] is None


async def test_legacy_timestamp_metadata_decodes_and_normalizes_to_utc(
    issued: IssuedAgentCredential,
) -> None:
    legacy = issued.metadata.model_dump(mode="json")
    legacy["expires_at"] = "2030-01-02T02:00:00+02:00"

    decoded = AGENT_METADATA.codec.decode(legacy)

    assert decoded.model_dump(mode="json")["expires_at"] == "2030-01-02T00:00:00Z"


async def test_all_management_operations_deny_callers_without_exact_admin_membership(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
    issued: IssuedAgentCredential,
) -> None:
    caller = AdministratorPrincipal(
        memberships=("Administrators", create_request.group_id)
    )
    agent_id = issued.metadata.agent_id
    with pytest.raises(AdministratorAccessDenied):
        await service.create(caller, create_request)
    with pytest.raises(AdministratorAccessDenied):
        await service.list_agents(caller)
    with pytest.raises(AdministratorAccessDenied):
        await service.rotate(
            caller,
            RotateAgentCredential(
                agent_id=agent_id, expires_at=create_request.expires_at
            ),
        )
    with pytest.raises(AdministratorAccessDenied):
        await service.revoke(caller, agent_id)
    assert await service.list_agents(administrator) == (issued.metadata,)


@pytest.mark.parametrize("invalid", ["blank_name", "missing_group", "naive_expiry"])
async def test_creation_rejects_invalid_requests(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
    invalid: Literal["blank_name", "missing_group", "naive_expiry"],
) -> None:
    values = create_request.model_dump()
    match invalid:
        case "blank_name":
            values["display_name"] = " \t"
        case "missing_group":
            del values["group_id"]
        case "naive_expiry":
            expiry = create_request.expires_at
            assert isinstance(expiry, datetime)
            values["expires_at"] = expiry.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        await service.create(administrator, CreateAgent.model_validate(values))
    assert await service.list_agents(administrator) == ()


async def test_creation_rejects_nonexistent_exact_group_id(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
) -> None:
    with pytest.raises(AgentGroupNotFound):
        await service.create(
            administrator,
            create_request.model_copy(update={"group_id": "agent-group "}),
        )
    assert await service.list_agents(administrator) == ()


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(seconds=-1)])
async def test_creation_rejects_expiry_at_or_before_the_current_time(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
    clock: MutableClock,
    offset: timedelta,
) -> None:
    with pytest.raises(ValueError, match="Expiry must be in the future"):
        await service.create(
            administrator,
            create_request.model_copy(update={"expires_at": clock.now() + offset}),
        )
    assert await service.list_agents(administrator) == ()


async def test_revocation_is_idempotent_and_retains_metadata(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    issued: IssuedAgentCredential,
) -> None:
    agent_id = issued.metadata.agent_id
    assert await service.revoke(administrator, agent_id)
    assert not await service.revoke(administrator, agent_id)
    assert await service.list_agents(administrator) == (
        issued.metadata.model_copy(update={"status": AgentCredentialStatus.REVOKED}),
    )
    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(issued.token)


@pytest.mark.parametrize("previous_state", ["active", "expired", "revoked"])
async def test_rotation_replaces_the_bearer_without_changing_the_agent(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    clock: MutableClock,
    issued: IssuedAgentCredential,
    previous_state: Literal["active", "expired", "revoked"],
) -> None:
    previous = issued.metadata
    if previous_state == "expired":
        expiry = previous.expires_at
        assert isinstance(expiry, datetime)
        clock.instant = expiry
    if previous_state == "revoked":
        await service.revoke(administrator, previous.agent_id)

    expires_at = clock.now() + timedelta(days=2)
    replacement = await service.rotate(
        administrator,
        RotateAgentCredential(agent_id=previous.agent_id, expires_at=expires_at),
    )

    current = replacement.metadata
    assert current == previous.model_copy(
        update={"credential_id": current.credential_id, "expires_at": expires_at}
    )
    assert current.credential_id != previous.credential_id
    assert replacement.token != issued.token
    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(issued.token)
    assert (
        await service.verify_for_public_mcp(replacement.token)
    ).agent_id == previous.agent_id


async def test_rotating_a_non_expiring_credential_can_set_a_finite_expiry(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    clock: MutableClock,
    non_expiring: IssuedAgentCredential,
) -> None:
    agent_id = non_expiring.metadata.agent_id
    expires_at = clock.now() + timedelta(days=1)

    replacement = await service.rotate(
        administrator, RotateAgentCredential(agent_id=agent_id, expires_at=expires_at)
    )

    assert replacement.metadata.expires_at == expires_at
    assert await service.list_agents(administrator) == (replacement.metadata,)
    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(non_expiring.token)


async def test_rotation_rejects_a_deleted_group_but_metadata_remains_manageable(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    group_management: GroupManagementService,
    issued: IssuedAgentCredential,
) -> None:
    metadata = issued.metadata
    await group_management.delete_group(metadata.group_id)
    with pytest.raises(AgentGroupNotFound):
        await service.rotate(
            administrator,
            RotateAgentCredential(
                agent_id=metadata.agent_id, expires_at=metadata.expires_at
            ),
        )
    assert await service.list_agents(administrator) == (metadata,)
    assert await service.revoke(administrator, metadata.agent_id)


async def test_rotation_cannot_rebind_an_agent_to_a_recreated_group(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    group_management: GroupManagementService,
    issued: IssuedAgentCredential,
) -> None:
    metadata = issued.metadata
    await group_management.delete_group(metadata.group_id)
    await group_management.register_group(RegisterGroup(group_id=metadata.group_id))

    with pytest.raises(AgentGroupNotFound):
        await service.rotate(
            administrator,
            RotateAgentCredential(
                agent_id=metadata.agent_id, expires_at=metadata.expires_at
            ),
        )

    assert await service.list_agents(administrator) == (metadata,)


async def test_rotation_with_nonfuture_expiry_preserves_current_credential(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    clock: MutableClock,
    issued: IssuedAgentCredential,
) -> None:
    with pytest.raises(ValueError, match="Expiry must be in the future"):
        await service.rotate(
            administrator,
            RotateAgentCredential(
                agent_id=issued.metadata.agent_id, expires_at=clock.now()
            ),
        )
    assert await service.list_agents(administrator) == (issued.metadata,)
    assert (
        await service.verify_for_public_mcp(issued.token)
    ).agent_id == issued.metadata.agent_id


async def test_agent_id_collision_cannot_overwrite_an_existing_agent(
    access: AdministratorAccess,
    administrator: AdministratorPrincipal,
    groups: MutableGroups,
    store: DatabaseAgentCredentialStore,
    clock: MutableClock,
    create_request: CreateAgent,
    issued: IssuedAgentCredential,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = SecureAgentCredentialGenerator()
    ids = iter((UUID(hex=issued.metadata.agent_id), UUID(int=1)))
    monkeypatch.setattr(generator, "generate_id", ids.__next__)
    service = AgentCredentialService(access, groups, store, clock, generator)

    with pytest.raises(AgentCredentialConflict, match="Agent ID already exists"):
        await service.create(administrator, create_request)

    assert await service.list_agents(administrator) == (issued.metadata,)
    assert (
        await service.verify_for_public_mcp(issued.token)
    ).agent_id == issued.metadata.agent_id
