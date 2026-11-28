from base64 import urlsafe_b64decode
from datetime import datetime, timedelta

import pytest
from pydantic import SecretStr

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.agent_tokens import (
    AgentCredentialService,
    CreateAgent,
    InvalidAgentCredential,
    IssuedAgentCredential,
    PublicMcpAgentIdentity,
)
from umbod.core.groups import (
    GroupManagementService,
    RegisterGroupMetadata,
    UpdateGroupMetadata,
)
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator

from .conftest import MutableClock, MutableGroups

pytestmark = pytest.mark.asyncio


async def test_current_bearer_verifies_as_only_the_assigned_public_mcp_agent(
    service: AgentCredentialService,
    groups: MutableGroups,
    issued: IssuedAgentCredential,
) -> None:
    group = await groups.find_group_instance(issued.metadata.group_id)
    assert group is not None
    prefix = f"umbod_agent_v1_{issued.metadata.agent_id}_"
    bearer = issued.token.get_secret_value()
    assert bearer.startswith(prefix)
    assert len(urlsafe_b64decode(bearer.removeprefix(prefix) + "=")) >= 32
    assert await service.verify_for_public_mcp(issued.token) == PublicMcpAgentIdentity(
        agent_id=issued.metadata.agent_id,
        group_id=issued.metadata.group_id,
        group_instance_id=group.instance_id,
        audience="umbod:mcp",
    )


async def test_wrong_secret_with_the_same_public_agent_locator_is_denied(
    service: AgentCredentialService, issued: IssuedAgentCredential
) -> None:
    bearer = issued.token.get_secret_value()
    wrong = bearer[:-1] + ("A" if not bearer.endswith("A") else "B")
    with pytest.raises(
        InvalidAgentCredential, match="^Invalid agent credential$"
    ) as failure:
        await service.verify_for_public_mcp(SecretStr(wrong))
    assert wrong not in repr(failure.value)


@pytest.mark.parametrize(
    "bearer",
    [
        "",
        "x" * 100_000,
        "umbod_agent_v1_" + "f" * 32 + "_" + "A" * 43,
        "umbod_agent_v1_" + "0" * 32 + "_" + "é" * 43,
    ],
    ids=["empty", "oversized", "unknown", "non_ascii"],
)
async def test_malformed_and_unknown_bearers_are_denied_uniformly(
    service: AgentCredentialService, bearer: str
) -> None:
    with pytest.raises(InvalidAgentCredential, match="^Invalid agent credential$"):
        await service.verify_for_public_mcp(SecretStr(bearer))


async def test_personal_access_token_cannot_verify_as_an_agent(
    service: AgentCredentialService,
) -> None:
    generated = SecurePersonalAccessTokenGenerator().generate()
    with pytest.raises(InvalidAgentCredential, match="^Invalid agent credential$"):
        await service.verify_for_public_mcp(generated.token)


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(seconds=1)])
async def test_verification_denies_at_and_after_expiry(
    service: AgentCredentialService,
    clock: MutableClock,
    issued: IssuedAgentCredential,
    offset: timedelta,
) -> None:
    expiry = issued.metadata.expires_at
    assert isinstance(expiry, datetime)
    clock.instant = expiry + offset
    with pytest.raises(InvalidAgentCredential, match="^Invalid agent credential$"):
        await service.verify_for_public_mcp(issued.token)


async def test_non_expiring_credentials_still_verify_after_the_clock_advances(
    service: AgentCredentialService,
    clock: MutableClock,
    non_expiring: IssuedAgentCredential,
) -> None:
    clock.instant += timedelta(days=36500)

    verified = await service.verify_for_public_mcp(non_expiring.token)
    assert verified.agent_id == non_expiring.metadata.agent_id


async def test_verification_denies_a_revoked_non_expiring_credential(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    non_expiring: IssuedAgentCredential,
) -> None:
    assert await service.revoke(administrator, non_expiring.metadata.agent_id)

    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(non_expiring.token)


async def test_verification_denies_when_group_id_is_deleted_even_with_same_label_present(
    service: AgentCredentialService,
    group_management: GroupManagementService,
    issued: IssuedAgentCredential,
) -> None:
    await group_management.delete_group(issued.metadata.group_id)
    await group_management.register_group_metadata(
        RegisterGroupMetadata(group_id="unrelated", label="Agent group", description="")
    )
    with pytest.raises(InvalidAgentCredential, match="^Invalid agent credential$"):
        await service.verify_for_public_mcp(issued.token)


async def test_recreating_the_group_does_not_reactivate_an_old_token(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    group_management: GroupManagementService,
    create_request: CreateAgent,
    issued: IssuedAgentCredential,
) -> None:
    original = await service.verify_for_public_mcp(issued.token)
    await group_management.delete_group(original.group_id)
    await group_management.register_group_metadata(
        RegisterGroupMetadata(
            group_id=original.group_id, label="Agent group", description=""
        )
    )
    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(issued.token)

    replacement = await service.create(administrator, create_request)
    verified = await service.verify_for_public_mcp(replacement.token)
    assert verified.group_id == original.group_id
    assert verified.group_instance_id != original.group_instance_id


async def test_editing_group_metadata_preserves_token_verification(
    service: AgentCredentialService,
    group_management: GroupManagementService,
    issued: IssuedAgentCredential,
) -> None:
    original = await service.verify_for_public_mcp(issued.token)
    await group_management.update_group_metadata(
        original.group_id,
        UpdateGroupMetadata(
            label="Renamed", description="Updated", expected_revision=1
        ),
    )

    assert await service.verify_for_public_mcp(issued.token) == original


async def test_verification_denies_when_the_group_catalogue_cannot_be_read(
    service: AgentCredentialService,
    groups: MutableGroups,
    issued: IssuedAgentCredential,
) -> None:
    groups.available = False
    with pytest.raises(InvalidAgentCredential, match="^Invalid agent credential$"):
        await service.verify_for_public_mcp(issued.token)
