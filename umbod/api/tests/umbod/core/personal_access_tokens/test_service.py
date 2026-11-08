from datetime import timedelta
from typing import cast

import pytest
from pydantic import SecretStr

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.core.personal_access_tokens import (
    InvalidPersonalAccessToken,
    IssuePersonalAccessToken,
    PersonalAccessTokenService,
    PersonalAccessTokenStatus,
    UntrustedPersonalAccessTokenCaller,
    ValidatePersonalAccessToken,
)

from umbod.core.personal_access_tokens.models import StoredPersonalAccessToken
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore

from .conftest import MutableClock

pytestmark = pytest.mark.asyncio


def validation(token: SecretStr) -> ValidatePersonalAccessToken:
    return ValidatePersonalAccessToken(
        token=token, audience="telemetry", required_scopes=("telemetry:read",)
    )


async def test_issue_generates_unique_tokens_and_ids(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
) -> None:
    first = await service.issue(caller, request_token)
    second = await service.issue(caller, request_token)
    assert first.token != second.token
    assert first.metadata.token_id != second.metadata.token_id
    assert await service.validate(validation(first.token)) == first.metadata


async def test_issue_and_validation_mask_bearer_in_representations(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
) -> None:
    issued = await service.issue(caller, request_token)
    bearer = issued.token.get_secret_value()
    for model in (issued, validation(issued.token)):
        assert bearer not in repr(model)
        assert bearer not in model.model_dump_json()
    assert "digest" not in issued.model_dump_json()


async def test_listing_exposes_only_metadata_in_deterministic_order(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
) -> None:
    issued = [await service.issue(caller, request_token) for _ in range(3)]
    listed = await service.list_tokens(caller)
    assert listed == tuple(
        sorted(
            (item.metadata for item in issued),
            key=lambda item: (item.created_at, item.token_id),
        )
    )
    for metadata in listed:
        assert "digest" not in metadata.model_dump()
        assert "token" not in metadata.model_dump()


@pytest.mark.parametrize(
    "issuer,subject",
    [
        ("other", "alice"),
        ("https://issuer", "bob"),
        ("https://issuer ", "alice"),
        ("https://issuer", "Alice"),
    ],
)
async def test_other_identities_cannot_list_or_revoke(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    issuer: str,
    subject: str,
) -> None:
    issued = await service.issue(caller, request_token)
    other = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
    )
    assert await service.list_tokens(other) == ()
    assert not await service.revoke(other, issued.metadata.token_id)
    assert not await service.revoke(other, "0" * 32)
    assert await service.validate(validation(issued.token)) == issued.metadata


async def test_owner_revocation_deletes_token_and_validation_is_immediately_denied(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    store: DatabasePersonalAccessTokenStore,
) -> None:
    issued = await service.issue(caller, request_token)
    retained = await service.issue(caller, request_token)
    assert await service.revoke(caller, issued.metadata.token_id)
    assert not await service.revoke(caller, issued.metadata.token_id)
    assert await store.find(issued.metadata.token_id) is None
    assert await service.list_tokens(caller) == (retained.metadata,)
    with pytest.raises(
        InvalidPersonalAccessToken, match="^Invalid personal access token$"
    ):
        await service.validate(validation(issued.token))


async def test_legacy_revoked_token_remains_readable_and_can_be_deleted(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    store: DatabasePersonalAccessTokenStore,
) -> None:
    issued = await service.issue(caller, request_token)
    metadata = issued.metadata.model_copy(
        update={"token_id": "f" * 32, "status": PersonalAccessTokenStatus.REVOKED}
    )
    assert await store.insert(StoredPersonalAccessToken(metadata=metadata, digest="0" * 64))
    assert metadata in await service.list_tokens(caller)
    foreign = caller.model_copy(
        update={"subject": caller.subject.model_copy(update={"subject": "bob"})}
    )
    assert not await service.revoke(foreign, metadata.token_id)
    assert await store.find(metadata.token_id) is not None
    assert await service.revoke(caller, metadata.token_id)
    assert await store.find(metadata.token_id) is None
    assert await service.list_tokens(caller) == (issued.metadata,)
    assert not await service.revoke(caller, metadata.token_id)


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(seconds=1)])
async def test_validation_denies_at_and_after_expiry(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    clock: MutableClock,
    offset: timedelta,
) -> None:
    issued = await service.issue(caller, request_token)
    clock.instant = request_token.expires_at + offset
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(validation(issued.token))


@pytest.mark.parametrize(
    "audience,scopes",
    [
        ("wrong", ("telemetry:read",)),
        ("telemetry", ("telemetry:write",)),
        ("telemetry", ("telemetry:read", "telemetry:write")),
    ],
)
async def test_validation_denies_wrong_audience_or_missing_exact_scope(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    audience: str,
    scopes: tuple[str, ...],
) -> None:
    issued = await service.issue(caller, request_token)
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(
            ValidatePersonalAccessToken(
                token=issued.token, audience=audience, required_scopes=scopes
            )
        )


@pytest.mark.parametrize(
    "bearer",
    [
        "",
        "not-a-token",
        "x" * 100000,
        "é" * 89,
        "umbod_pat_v1_" + "0" * 32 + "_" + "a" * 43,
    ],
    ids=["empty", "malformed", "oversized", "nonascii", "unknown"],
)
async def test_malformed_or_unknown_tokens_have_credential_free_uniform_errors(
    service: PersonalAccessTokenService,
    bearer: str,
) -> None:
    with pytest.raises(InvalidPersonalAccessToken) as failure:
        await service.validate(validation(SecretStr(bearer)))
    assert str(failure.value) == "Invalid personal access token"


async def test_tampered_secret_is_rejected(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
) -> None:
    issued = await service.issue(caller, request_token)
    bearer = issued.token.get_secret_value()
    tampered = bearer[:-1] + ("A" if bearer[-1] != "A" else "B")
    with pytest.raises(InvalidPersonalAccessToken):
        await service.validate(validation(SecretStr(tampered)))


@pytest.mark.parametrize(
    "authentication",
    [
        value
        for value in AuthenticationProvenance
        if value != AuthenticationProvenance.UPSTREAM_VERIFIED
    ],
)
async def test_management_rejects_untrusted_authentication(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    request_token: IssuePersonalAccessToken,
    authentication: AuthenticationProvenance,
) -> None:
    untrusted = CallerContext(
        authentication=authentication,
        subject=UnavailableSubject(kind="unavailable")
        if authentication == AuthenticationProvenance.UNAVAILABLE
        else caller.subject,
    )
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.issue(untrusted, request_token)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.list_tokens(untrusted)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.revoke(untrusted, "0" * 32)


@pytest.mark.parametrize(
    "identity",
    [
        UnavailableSubject(kind="unavailable"),
        SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
        SubjectIdentity(issuer=DeclaredIssuer(value=" "), subject="alice"),
        SubjectIdentity(issuer=DeclaredIssuer(value="issuer"), subject=" "),
    ],
)
async def test_management_rejects_missing_identity(
    service: PersonalAccessTokenService,
    request_token: IssuePersonalAccessToken,
    identity: SubjectIdentity | UnavailableSubject,
) -> None:
    caller = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=identity
    )
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.issue(caller, request_token)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.list_tokens(caller)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.revoke(caller, "0" * 32)


async def test_management_fails_closed_when_caller_is_missing(
    service: PersonalAccessTokenService,
) -> None:
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.list_tokens(cast(CallerContext, None))


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(seconds=-1)])
async def test_issue_rejects_nonfuture_expiry(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    clock: MutableClock,
    offset: timedelta,
) -> None:
    request = IssuePersonalAccessToken(
        name="name",
        audience="audience",
        scopes=("telemetry:read",),
        expires_at=clock.now() + offset,
    )
    with pytest.raises(ValueError, match="future"):
        await service.issue(caller, request)


async def test_issue_rejects_scopes_outside_configured_policy(
    service: PersonalAccessTokenService,
    caller: CallerContext,
    clock: MutableClock,
) -> None:
    request = IssuePersonalAccessToken(
        name="name",
        audience="audience",
        scopes=("other:read",),
        expires_at=clock.now() + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="Unsupported"):
        await service.issue(caller, request)
    assert await service.list_tokens(caller) == ()
