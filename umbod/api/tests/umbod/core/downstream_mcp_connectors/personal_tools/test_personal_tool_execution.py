from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, replace_policy, save_matches
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.connectors.downstream_mcp.personal_connections import Authorized, CanonicalPrincipal, PersonalConnectionKey, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import UnknownPersonalTokenLifetime, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime, PersonalRuntimeContext, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE, CONNECTOR_PERMISSION_TABLE
from umbod.core.persistence import DeleteQuery, NoFilter, TransactionMode

from .runtime_support import execution_case

__all__ = ["runtime_case"]


@pytest.mark.asyncio
async def test_execution_uses_current_owner_without_list_or_result_cache(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    assert len(await execution.runtime.list_tools()) == 1
    assert execution.transport.list_requests == []
    first = await execution.runtime.execute(execution.command)
    execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "fresh"}})
    second = await execution.runtime.execute(execution.command)
    assert first.result["structuredContent"] != second.result["structuredContent"]
    assert len(execution.transport.calls) == 2
    assert "owner-token" not in str(first)


@pytest.mark.asyncio
async def test_same_connector_and_arguments_use_two_owners_tokens_and_data(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    first = await execution.runtime.execute(execution.command)
    key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="second"), connector_id="personal")
    await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    query = runtime_case.query.model_copy(update={"key": key})
    grant = runtime_case.grant.model_copy(update={"key": key, "access_token": SecretStr("second-token")})
    other = RuntimeCase(runtime_case.database, runtime_case.bundle, runtime_case.store, query, grant)
    await install_authorization(other, authorize_personal_grant(grant))
    policy = await replace_policy(other, (approved_tool("read"),))
    await save_matches(other, policy)
    execution.transport.inventories[key] = execution.transport.inventories[runtime_case.query.key]
    execution.transport.results[(key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "second"}})
    execution.contexts.contexts[:] = [PersonalRuntimeContext(principal=key.principal, group_ids=("team",))]
    second = await execution.runtime.execute(execution.command)
    assert first.result["structuredContent"] == {"owner": "owner"}
    assert second.result["structuredContent"] == {"owner": "second"}
    assert [call.target.access_token.get_secret_value() for call in execution.transport.calls] == ["owner-token", "second-token"]
    assert execution.transport.calls[0].arguments == execution.transport.calls[1].arguments


@pytest.mark.asyncio
async def test_missing_context_and_disabled_runtime_never_fall_back(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    execution.contexts.contexts.clear()
    for runtime in (execution.runtime, DisabledPersonalToolRuntime()):
        assert await runtime.list_tools() == ()
        with pytest.raises(PersonalRuntimeUnavailable, match="^Personal tool unavailable$"):
            await runtime.execute(execution.command)
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ("disable", "disconnect", "publication", "activation", "connector_grant", "capability_grant", "policy", "rotation", "expired", "unknown_lifetime", "legacy", "corrupt", "foreign"))
async def test_current_admission_rejects_withdrawn_or_invalid_authority(runtime_case: RuntimeCase, revocation: str) -> None:
    execution = await execution_case(runtime_case)
    if revocation == "disable":
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    elif revocation == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif revocation == "publication":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    elif revocation == "activation":
        await runtime_case.bundle.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), ActivationStatus.DISABLED)
    elif revocation in ("connector_grant", "capability_grant"):
        async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(CONNECTOR_PERMISSION_TABLE if revocation == "connector_grant" else CAPABILITY_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    elif revocation == "policy":
        await replace_policy(runtime_case, ())
    elif revocation == "foreign":
        execution.contexts.contexts[:] = [PersonalRuntimeContext(principal=CanonicalPrincipal(namespace="trusted", subject="stranger"), group_ids=("team",))]
    else:
        grant = runtime_case.grant
        if revocation == "expired":
            grant = grant.model_copy(update={"lifetime": grant.lifetime.model_copy(update={"expires_at": runtime_case.query.now - timedelta(seconds=1)})})
        elif revocation == "unknown_lifetime":
            grant = grant.model_copy(update={"lifetime": UnknownPersonalTokenLifetime()})
        else:
            grant = grant.model_copy(update={"access_token": SecretStr("rotated-token")})
        authorization = authorize_personal_grant(grant)
        if revocation in ("legacy", "corrupt"):
            authorization = Authorized(authorization=SecretStr('{"access_token":"legacy-secret"}' if revocation == "legacy" else "corrupt-secret"))
        await install_authorization(runtime_case, authorization)
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await execution.runtime.execute(execution.command)
    assert str(caught.value) == "Personal tool unavailable"
    assert caught.value.__context__ is None
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ("fingerprint", "revision", "foreign", "prompt", "arguments"))
async def test_held_contract_identity_and_arguments_are_revalidated(runtime_case: RuntimeCase, invalidity: str) -> None:
    execution = await execution_case(runtime_case)
    updates: dict[str, object] = {}
    if invalidity == "fingerprint":
        updates["fingerprint"] = "0" * 64
    elif invalidity == "revision":
        updates["contract_revision"] = "old"
    elif invalidity == "foreign":
        updates["identity"] = execution.command.identity.model_copy(update={"connector_id": "other"})
    elif invalidity == "prompt":
        updates["identity"] = execution.command.identity.model_copy(update={"capability_kind": "prompt"})
    else:
        updates["arguments"] = {"value": 12}
    with pytest.raises(PersonalRuntimeUnavailable):
        await execution.runtime.execute(execution.command.model_copy(update=updates))
    assert execution.transport.calls == []


@pytest.mark.asyncio
async def test_recreated_worker_uses_persisted_authority(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    stores = await create_downstream_mcp_stores("runtime-secret", runtime_case.database)
    runtime = PersonalToolRuntimeService(execution.contexts, stores.definitions, stores.personal_tool_access, execution.transport, lambda: runtime_case.query.now)
    assert len(await runtime.list_tools()) == 1
    assert (await runtime.execute(execution.command)).result["structuredContent"] == {"owner": "owner"}


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ({}, {"content": [], "isError": True}, {"content": [], "structuredContent": None}, {"content": [], "structuredContent": "secret"}))
async def test_malformed_or_downstream_error_results_are_safe(runtime_case: RuntimeCase, result: dict[str, object]) -> None:
    execution = await execution_case(runtime_case)
    execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result=result)
    with pytest.raises(PersonalRuntimeUnavailable, match="^Personal tool unavailable$"):
        await execution.runtime.execute(execution.command)
