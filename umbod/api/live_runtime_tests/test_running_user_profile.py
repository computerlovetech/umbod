import os

import httpx
import pytest

from conftest import RuntimeEndpoints
from umbod.rest.users.responses import UserProfileResponse


@pytest.mark.parametrize("token_variable,subject,name,administration", [
    ("UMBOD_TEST_BEARER_TOKEN", "kind-ci", "Kind Alice", True),
    ("UMBOD_TEST_MEMBER_BEARER_TOKEN", "kind-member", "Kind Member", False),
])
def test_running_profile_returns_identity_and_effective_capabilities_for_both_roles(
    runtime_endpoints: RuntimeEndpoints,
    token_variable: str,
    subject: str,
    name: str,
    administration: bool,
) -> None:
    headers = {"Authorization": "Bearer " + os.environ[token_variable]}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30) as client:
        response = client.get("/api/me/profile")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        profile = UserProfileResponse.model_validate(response.json())
        assert profile.user.id == subject
        assert profile.user.name == name
        assert profile.user.email == subject + "@example.invalid"
        assert profile.user.picture == "https://images.example.invalid/" + subject + ".png"
        assert profile.capabilities.administration is administration
        protected = client.get("/api/admin/mcp-permissions/groups")
        assert protected.status_code == (200 if administration else 403), protected.text


def test_running_profile_rejects_unauthenticated_requests(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        response = client.get("/api/me/profile")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
