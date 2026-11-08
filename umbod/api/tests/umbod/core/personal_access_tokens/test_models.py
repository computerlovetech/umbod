from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from umbod.core.personal_access_tokens import (
    IssuePersonalAccessToken,
    PersonalAccessTokenPolicy,
    TokenOwner,
)


@pytest.mark.parametrize(
    "scopes",
    [
        (),
        ("read", "read"),
        ("",),
        (" ",),
        ("telemetry:*",),
        ("telemetry: read",),
        ("a\nb",),
        tuple(f"scope:{number}" for number in range(65)),
    ],
)
def test_policy_and_request_reject_invalid_scopes(scopes: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        PersonalAccessTokenPolicy(allowed_scopes=scopes)
    with pytest.raises(ValidationError):
        IssuePersonalAccessToken(
            name="name",
            audience="telemetry",
            scopes=scopes,
            expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", " "),
        ("name", "a" * 257),
        ("audience", ""),
        ("audience", " "),
        ("audience", "a" * 257),
    ],
)
def test_request_rejects_blank_or_oversized_text(field: str, value: str) -> None:
    payload: dict[str, object] = {
        "name": "name",
        "audience": "audience",
        "scopes": ("telemetry:read",),
        "expires_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        IssuePersonalAccessToken.model_validate(payload)


def test_request_rejects_naive_expiry() -> None:
    with pytest.raises(ValidationError):
        IssuePersonalAccessToken(
            name="name",
            audience="audience",
            scopes=("read",),
            expires_at=datetime(2030, 1, 1),
        )


@pytest.mark.parametrize(
    "issuer,subject",
    [("", "alice"), ("issuer", " "), ("a" * 4097, "alice"), ("issuer", "a" * 4097)],
)
def test_owner_rejects_blank_or_oversized_identity(issuer: str, subject: str) -> None:
    with pytest.raises(ValidationError):
        TokenOwner(issuer=issuer, subject=subject)
