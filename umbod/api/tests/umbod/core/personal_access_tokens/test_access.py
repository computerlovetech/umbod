import pytest
from pydantic import ValidationError

from umbod.core.personal_access_tokens import (
    PersonalAccessTokenAccess,
    PersonalAccessTokenGrant,
    PersonalAccessTokenPermission,
    PersonalAccessTokenResource,
    ResolvedPersonalAccessTokenAccess,
    personal_access_token_policy,
    resolve_personal_access_token_access,
)
from umbod.core.personal_access_tokens.access import (
    TELEMETRY_INGEST_SCOPE,
    TELEMETRY_TOKEN_AUDIENCE,
)


def test_supported_grants_resolve_to_exact_audience_and_policy_scopes() -> None:
    for resource in PersonalAccessTokenResource:
        for permission in PersonalAccessTokenPermission:
            resolved = resolve_personal_access_token_access(
                PersonalAccessTokenAccess(
                    grants=(
                        PersonalAccessTokenGrant(
                            resource=resource, permission=permission
                        ),
                    )
                )
            )
            assert resolved.audience == TELEMETRY_TOKEN_AUDIENCE == "umbod:telemetry"
            assert resolved.scopes == (TELEMETRY_INGEST_SCOPE,) == ("telemetry:write",)
            assert resolved.scopes == personal_access_token_policy().allowed_scopes


@pytest.mark.parametrize(
    "grants",
    [
        (),
        (
            {"resource": "telemetry", "permission": "write"},
            {"resource": "telemetry", "permission": "write"},
        ),
    ],
)
def test_access_rejects_empty_or_duplicate_resources(
    grants: tuple[dict[str, str], ...],
) -> None:
    with pytest.raises(ValidationError):
        PersonalAccessTokenAccess.model_validate({"grants": grants})


@pytest.mark.parametrize(
    "grant",
    [
        {},
        {"resource": "telemetry"},
        {"resource": "unknown", "permission": "write"},
        {"resource": "telemetry", "permission": "read"},
        {"resource": "telemetry", "permission": "admin"},
        {"resource": "/api/telemetry/v1/traces", "permission": "write"},
        {"resource": "https://example.test/api", "permission": "write"},
        {"resource": "*", "permission": "write"},
        {"resource": "telemetry", "permission": "*"},
        {"resource": "telemetry", "permission": "write", "audience": "other"},
    ],
)
def test_grant_rejects_unsupported_or_incomplete_authority(
    grant: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PersonalAccessTokenGrant.model_validate(grant)


@pytest.mark.parametrize(
    "model,field,value",
    [
        (
            PersonalAccessTokenGrant(
                resource=PersonalAccessTokenResource.TELEMETRY,
                permission=PersonalAccessTokenPermission.WRITE,
            ),
            "resource",
            "other",
        ),
        (
            PersonalAccessTokenAccess(
                grants=(
                    PersonalAccessTokenGrant(
                        resource=PersonalAccessTokenResource.TELEMETRY,
                        permission=PersonalAccessTokenPermission.WRITE,
                    ),
                )
            ),
            "grants",
            (),
        ),
        (
            ResolvedPersonalAccessTokenAccess(
                audience="umbod:telemetry", scopes=("telemetry:write",)
            ),
            "audience",
            "other",
        ),
    ],
)
def test_access_models_are_immutable_and_forbid_extra_fields(
    model: PersonalAccessTokenGrant
    | PersonalAccessTokenAccess
    | ResolvedPersonalAccessTokenAccess,
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        setattr(model, field, value)
    with pytest.raises(ValidationError):
        type(model).model_validate(model.model_dump() | {"unknown": "value"})


@pytest.mark.parametrize(
    "resolved",
    [
        {"audience": "", "scopes": ["telemetry:write"]},
        {"audience": "umbod:telemetry", "scopes": []},
        {"audience": "umbod:telemetry", "scopes": ["*"]},
    ],
)
def test_resolved_access_validates_audience_and_scopes(
    resolved: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ResolvedPersonalAccessTokenAccess.model_validate(resolved)
