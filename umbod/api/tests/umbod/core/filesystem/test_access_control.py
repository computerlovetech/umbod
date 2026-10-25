from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError

from umbod.core.filesystem import (
    AccessControlDriver,
    AccessGrant,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
)
from umbod.infrastructure import create_access_control_driver
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime


@pytest_asyncio.fixture(params=["inmemory", "sqlite"])
async def policies(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[AccessControlDriver]:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "policies.db")
    )
    try:
        yield create_access_control_driver(database=runtime.database)
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize(
    "missing_field", ["permissions", "recursive", "principal", "node_id"]
)
def test_grant_contract_requires_explicit_fields(missing_field: str) -> None:
    values: dict[str, object] = {
        "node_id": uuid4(),
        "principal": Principal(type=PrincipalType.USER, issuer="provider", id="one"),
        "permissions": set(),
        "recursive": False,
    }
    del values[missing_field]
    with pytest.raises(ValidationError):
        AccessGrant.model_validate(values)


def principal(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="provider", id=identifier)


@pytest.mark.asyncio
async def test_opaque_node_owner_is_missing_until_explicitly_assigned(
    policies: AccessControlDriver,
) -> None:
    node_id = uuid4()
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(node_id)
    first = Ownership(node_id=node_id, owner=principal("first"))
    await policies.set_owner(first)
    second = Ownership(node_id=node_id, owner=principal("second"))
    await policies.set_owner(second)
    assert await policies.get_owner(node_id) == second


@pytest.mark.asyncio
async def test_grant_replacement_preserves_empty_permissions_and_removal_is_idempotent(
    policies: AccessControlDriver,
) -> None:
    node_id = uuid4()
    subject = principal("reader")
    assert tuple(await policies.list_grants(node_id)) == ()
    await policies.add_grant(
        AccessGrant(
            node_id=node_id,
            principal=subject,
            permissions={Permission.READ},
            recursive=True,
        )
    )
    replacement = AccessGrant(
        node_id=node_id, principal=subject, permissions=set(), recursive=False
    )
    await policies.add_grant(replacement)
    await policies.add_grant(replacement)
    assert tuple(await policies.list_grants(node_id)) == (replacement,)
    await policies.remove_grant(node_id, subject)
    await policies.remove_grant(node_id, subject)
    assert tuple(await policies.list_grants(node_id)) == ()


@pytest.mark.asyncio
async def test_principal_identity_uses_all_three_components(
    policies: AccessControlDriver,
) -> None:
    node_id = uuid4()
    subjects = [
        principal("one"),
        principal("two"),
        Principal(type=PrincipalType.GROUP, issuer="provider", id="one"),
        Principal(type=PrincipalType.USER, issuer="other", id="one"),
    ]
    for subject in subjects:
        await policies.add_grant(
            AccessGrant(
                node_id=node_id,
                principal=subject,
                permissions={Permission.DISCOVER},
                recursive=False,
            )
        )
    await policies.remove_grant(node_id, subjects[0])
    assert {grant.principal for grant in await policies.list_grants(node_id)} == set(
        subjects[1:]
    )


@pytest.mark.asyncio
async def test_mutable_permission_observations_are_detached(
    policies: AccessControlDriver,
) -> None:
    node_id = uuid4()
    grant = AccessGrant(
        node_id=node_id,
        principal=principal("one"),
        permissions={Permission.READ},
        recursive=False,
    )
    await policies.add_grant(grant)
    grant.permissions.add(Permission.WRITE)
    observed = (await policies.list_grants(node_id))[0]
    assert observed.permissions == {Permission.READ}
    observed.permissions.clear()
    assert (await policies.list_grants(node_id))[0].permissions == {Permission.READ}
