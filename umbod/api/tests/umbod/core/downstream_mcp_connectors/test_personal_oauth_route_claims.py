import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import CallbackIssuer, GenericRoute, IssuerBinding, IssuerRoute, MissingCallbackIssuer, PresentCallbackIssuer, issuer_callback_uri, issuer_route_key
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import ClaimPersonalOAuthAttempt, PersonalOAuthUnavailable, PublishPersonalOAuthAttempt
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores

from test_personal_oauth_attempt_persistence import AttemptCase, case as case, publication


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ("wrong_hash", "cross_issuer", "generic", "mismatch", "empty", "wrong_state"))
async def test_route_or_issuer_mismatch_does_not_consume_bound_attempt(case: AttemptCase, attack: str) -> None:
    issuer = "https://issuer.example"
    issuer_key = issuer_route_key(issuer)
    binding = IssuerBinding(kind="issuer", expected_issuer=issuer, issuer_key=issuer_key,
                            redirect_uri=issuer_callback_uri(case.command.preparation.redirect_uri, issuer))
    await case.store.reserve(case.command)
    prepared = publication(case).prepared.model_copy(update={"callback_binding": binding})
    await case.store.publish(PublishPersonalOAuthAttempt(query=case.query, prepared=prepared))
    route = IssuerRoute(kind="issuer", issuer_key=issuer_key)
    command = ClaimPersonalOAuthAttempt(state=case.command.preparation.state, claim_id="claim", now=case.query.now,
                                       route=route, issuer=MissingCallbackIssuer(kind="missing"))
    update = {
        "wrong_hash": {"route": IssuerRoute(kind="issuer", issuer_key="0" * 64)},
        "cross_issuer": {"route": IssuerRoute(kind="issuer", issuer_key=issuer_route_key(issuer + "/"))},
        "generic": {"route": GenericRoute(kind="generic"), "issuer": PresentCallbackIssuer(kind="present", value=issuer)},
        "mismatch": {"issuer": PresentCallbackIssuer(kind="present", value=issuer + "/")},
        "empty": {"issuer": PresentCallbackIssuer.model_construct(kind="present", value="")},
        "wrong_state": {"state": SecretStr(case.command.attempt_id + ".wrong-secret")},
    }[attack]
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.claim(command.model_copy(update=update))
    assert (await case.store.get(case.query)).status == "pending"
    recreated = await create_downstream_mcp_stores("test-secret", case.database)
    claimed = await recreated.personal_oauth_attempts.claim(command)
    assert claimed.prepared.callback_binding == binding
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.claim(command)


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", (MissingCallbackIssuer(kind="missing"), PresentCallbackIssuer.model_construct(kind="present", value="")))
async def test_legacy_generic_requires_actual_nonempty_issuer_before_claim(case: AttemptCase, issuer: CallbackIssuer) -> None:
    await case.store.reserve(case.command)
    await case.store.publish(publication(case))
    command = ClaimPersonalOAuthAttempt.model_validate({
        "state": case.command.preparation.state, "claim_id": "claim", "now": case.query.now,
        "route": GenericRoute(kind="generic"), "issuer": issuer,
    })
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.claim(command)
    assert (await case.store.get(case.query)).status == "pending"
