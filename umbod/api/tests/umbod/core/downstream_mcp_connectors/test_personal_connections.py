from umbod.core.connectors.downstream_mcp.personal_connections import UnavailablePersonalCaller
from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import Mock

import pytest
import pytest_asyncio
from pydantic import SecretStr

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections import (
    Authorized,
    CanonicalPrincipal,
    InMemoryPersonalConnectionStore,
    MissingCanonicalPrincipal,
    MissingPersonalConnection,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionService,
    PersonalConnectionStore,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
    StalePersonalConnectionRevision,
    Unauthorized,
)
from umbod.core.connectors.downstream_mcp.stores.personal_connections import (
    EncryptedPersonalConnectionStore,
)


@pytest_asyncio.fixture(params=("inmemory", "sqlite"))
async def store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[PersonalConnectionStore]:
    if request.param == "inmemory":
        yield InMemoryPersonalConnectionStore()
    else:
        runtime = await prepared_sqlite_runtime(tmp_path / "personal.sqlite3")
        yield EncryptedPersonalConnectionStore(
            runtime.database, AuthenticatedTextCipher("personal-secret")
        )


def _key(
    subject: str = "owner", namespace: str = "trusted", connector_id: str = "alpha"
) -> PersonalConnectionKey:
    return PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace=namespace, subject=subject),
        connector_id=connector_id,
    )


async def _enabled(
    store: PersonalConnectionStore, key: PersonalConnectionKey
) -> PersonalConnection:
    state = await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert isinstance(state, PersonalConnection)
    return state


def _authorization(
    state: PersonalConnection, token: str = "private-token"
) -> ReplacePersonalAuthorization:
    return ReplacePersonalAuthorization(
        key=state.key,
        expected_revision=state.revision,
        authorization=Authorized(authorization=SecretStr(token)),
    )


@pytest.mark.asyncio
async def test_missing_state_is_disabled_unauthorized_and_lifecycle_is_idempotent(
    store: PersonalConnectionStore,
) -> None:
    key = _key()
    missing = await store.get(key)
    assert isinstance(missing, MissingPersonalConnection)
    assert missing.enabled is False
    assert isinstance(missing.authorization, Unauthorized)
    assert await store.disconnect(key) == missing
    assert (
        await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=False))
        == missing
    )
    enabled = await _enabled(store, key)
    assert isinstance(enabled.authorization, Unauthorized)
    assert await _enabled(store, key) == enabled


@pytest.mark.asyncio
async def test_disabling_retains_authorization_and_disconnect_clears_it(
    store: PersonalConnectionStore,
) -> None:
    enabled = await _enabled(store, _key())
    authorized = await store.replace_authorization(_authorization(enabled))
    disabled = await store.set_enabled(
        SetPersonalConnectionEnabled(key=enabled.key, enabled=False)
    )
    assert disabled.authorization == authorized.authorization
    assert not disabled.enabled
    assert disabled.revision != authorized.revision
    assert (
        await store.set_enabled(
            SetPersonalConnectionEnabled(key=enabled.key, enabled=False)
        )
        == disabled
    )
    disconnected = await store.disconnect(enabled.key)
    assert isinstance(disconnected.authorization, Unauthorized)
    assert not disconnected.enabled
    assert disconnected.revision != disabled.revision
    repeated = await store.disconnect(enabled.key)
    assert repeated.enabled == disconnected.enabled
    assert repeated.authorization == disconnected.authorization
    assert repeated.revision != disconnected.revision


@pytest.mark.parametrize(
    "other", (_key("other"), _key(namespace="another"), _key(connector_id="beta"))
)
@pytest.mark.asyncio
async def test_ownership_isolated_by_namespace_subject_and_connector(
    store: PersonalConnectionStore, other: PersonalConnectionKey
) -> None:
    before = await store.replace_authorization(
        _authorization(await _enabled(store, other), "other-token")
    )
    enabled = await _enabled(store, _key())
    await store.replace_authorization(_authorization(enabled))
    await store.set_enabled(
        SetPersonalConnectionEnabled(key=enabled.key, enabled=False)
    )
    await store.disconnect(enabled.key)
    assert await store.get(other) == before


@pytest.mark.asyncio
async def test_conditional_authorization_never_creates_missing_record(
    store: PersonalConnectionStore,
) -> None:
    command = ReplacePersonalAuthorization(
        key=_key(),
        expected_revision="missing",
        authorization=Authorized(authorization="secret"),
    )
    with pytest.raises(StalePersonalConnectionRevision):
        await store.replace_authorization(command)
    assert isinstance(await store.get(command.key), MissingPersonalConnection)


@pytest.mark.parametrize(
    "interruption", ("disconnect", "replacement", "disabled_disconnect")
)
@pytest.mark.asyncio
async def test_stale_revision_cannot_install_authorization(
    store: PersonalConnectionStore, interruption: str
) -> None:
    enabled = await _enabled(store, _key())
    if interruption == "disabled_disconnect":
        enabled = await store.set_enabled(
            SetPersonalConnectionEnabled(key=enabled.key, enabled=False)
        )
        assert isinstance(enabled, PersonalConnection)
        await store.disconnect(enabled.key)
    elif interruption == "disconnect":
        await store.disconnect(enabled.key)
        await _enabled(store, enabled.key)
    else:
        await store.replace_authorization(_authorization(enabled, "new-token"))
    with pytest.raises(StalePersonalConnectionRevision):
        await store.replace_authorization(_authorization(enabled))


@pytest.mark.asyncio
async def test_identical_authorization_replacement_preserves_revision(
    store: PersonalConnectionStore,
) -> None:
    state = await store.replace_authorization(
        _authorization(await _enabled(store, _key()))
    )
    assert isinstance(state, PersonalConnection)
    assert await store.replace_authorization(_authorization(state)) == state


@pytest.mark.asyncio
async def test_competing_replacements_only_one_revision_wins(
    store: PersonalConnectionStore,
) -> None:
    enabled = await _enabled(store, _key())
    results = await asyncio.gather(
        store.replace_authorization(_authorization(enabled, "one")),
        store.replace_authorization(_authorization(enabled, "two")),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PersonalConnection) for result in results) == 1
    assert (
        sum(isinstance(result, StalePersonalConnectionRevision) for result in results)
        == 1
    )


@pytest.mark.parametrize("disconnect_first", (True, False))
@pytest.mark.asyncio
async def test_disconnect_racing_authorization_cannot_restore_access(
    store: PersonalConnectionStore, disconnect_first: bool,
) -> None:
    enabled = await _enabled(store, _key())
    operations = (
        store.disconnect(enabled.key),
        store.replace_authorization(_authorization(enabled)),
    )
    if not disconnect_first:
        operations = tuple(reversed(operations))
    results = await asyncio.gather(*operations, return_exceptions=True)
    assert all(
        isinstance(result, (PersonalConnection, StalePersonalConnectionRevision))
        for result in results
    )
    current = await store.get(enabled.key)
    assert not current.enabled
    assert isinstance(current.authorization, Unauthorized)


@pytest.mark.asyncio
async def test_delete_connector_removes_all_owners_but_not_other_connectors(
    store: PersonalConnectionStore,
) -> None:
    keys = (_key(), _key("other"), _key(namespace="another"))
    for key in keys:
        await _enabled(store, key)
    remaining = await _enabled(store, _key(connector_id="beta"))
    await store.delete_connector("alpha")
    for key in keys:
        assert isinstance(await store.get(key), MissingPersonalConnection)
    assert await store.get(remaining.key) == remaining


@pytest.mark.parametrize("operation", ("get", "enable", "disconnect", "replace"))
@pytest.mark.asyncio
async def test_absent_principal_denied_before_any_storage_access(
    operation: str,
) -> None:
    store = Mock(spec=PersonalConnectionStore)
    service = PersonalConnectionService(UnavailablePersonalCaller(kind="unavailable"), store)
    with pytest.raises(MissingCanonicalPrincipal):
        if operation == "get":
            await service.get("alpha")
        elif operation == "enable":
            await service.set_enabled("alpha", True)
        elif operation == "disconnect":
            await service.disconnect("alpha")
        else:
            await service.replace_authorization(
                "alpha", "revision", SecretStr("secret")
            )
    assert store.mock_calls == []


@pytest.mark.asyncio
async def test_service_uses_only_validated_principal(
    store: PersonalConnectionStore,
) -> None:
    key = _key()
    service = PersonalConnectionService(captured_personal_caller(key.principal, ()), store)
    state = await service.set_enabled("alpha", True)
    assert state == await store.get(key)
