import pytest
from pydantic import ValidationError

from umbod.config import (
    AppConfig,
    OperatorSettings,
    build_app_config,
    inspect_app_config,
)


def test_profile_environment_build_and_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "UMBOD_PROFILE": "production",
        "UMBOD_AUTH": "auth0",
        "UMBOD_ROOT_SECRET": "root",
        "UMBOD_OIDC_DOMAIN": "identity.test",
        "UMBOD_OIDC_CLIENT_ID": "web",
        "UMBOD_OIDC_CLIENT_SECRET": "secret",
        "UMBOD_OIDC_AUDIENCE": "api",
        "UMBOD_USER_PROFILE_MODE": "id_token",
        "UMBOD_USER_PROFILE_JWT_HEADER": "X-Profile",
        "UMBOD_USER_PROFILE_NAME_CLAIM": "https://claims.test/name",
        "UMBOD_USER_PROFILE_EMAIL_CLAIM": "mail",
        "UMBOD_USER_PROFILE_PICTURE_CLAIM": "avatar",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.user_profile.model_dump() == {
        "mode": "id_token",
        "jwt_header_name": "X-Profile",
        "name_claim": "https://claims.test/name",
        "email_claim": "mail",
        "picture_claim": "avatar",
    }
    group = next(
        group
        for group in inspect_app_config(config).groups
        if group.id == "user_profile"
    )
    assert {entry.variable: entry.value for entry in group.entries} == {
        key: value
        for key, value in values.items()
        if key.startswith("UMBOD_USER_PROFILE_")
    }


@pytest.mark.parametrize(
    "profile",
    [
        {"mode": "invalid"},
        {"jwt_header_name": "Authorization"},
        {"jwt_header_name": "bad header"},
        {"jwt_header_name": ""},
        {"name_claim": " "},
        {"email_claim": ""},
        {"picture_claim": "\t"},
    ],
)
def test_invalid_profile_configuration_rejected(profile: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AppConfig(user_profile=profile)


def test_profile_header_cannot_equal_access_header() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        AppConfig(
            admin_authentication={"jwt_header_name": "x-profile"},
            user_profile={"jwt_header_name": "X-Profile"},
        )


@pytest.mark.parametrize(
    "mode,environment",
    [("simulation", "development"), ("disabled", "production"), ("jwt", "development")],
)
def test_id_profiles_require_real_jwt(mode: str, environment: str) -> None:
    with pytest.raises(ValidationError, match="real production JWT"):
        AppConfig(
            admin_authentication={"mode": mode, "environment": environment},
            user_profile={"mode": "id_token"},
        )


@pytest.mark.parametrize("missing", ["issuer", "jwks", "client"])
def test_id_profile_requires_verification_configuration(missing: str) -> None:
    with pytest.raises(ValidationError, match="issuer, client ID and admin JWKS"):
        AppConfig(
            admin_authentication={
                "mode": "jwt",
                "environment": "production",
                "jwks_url": "" if missing == "jwks" else "https://identity.test/jwks",
            },
            oidc={
                "issuer_url": "" if missing == "issuer" else "https://identity.test/",
                "client_id": "" if missing == "client" else "web",
            },
            user_profile={"mode": "id_token"},
        )


def test_default_profile_preserves_access_claims_mode() -> None:
    assert (
        build_app_config(OperatorSettings(_env_file=None)).user_profile.mode
        == "access_claims"
    )
