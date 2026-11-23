import re
from unittest.mock import AsyncMock

import pytest
from httpx import Response

from umbod.config import AppConfig
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER

from .conftest import SetupApi

PREPARE = "/api/me/telemetry/install-claims"
REDEEM = "/api/install/v1/codex/telemetry/redeem"
TOKENS = "/api/me/personal-access-tokens"


def create_claim(api: SetupApi) -> str:
    return api.client.post(PREPARE, json={"harness": "codex"}).json()["code"]


def redeem(api: SetupApi, code: str, path: str = REDEEM) -> Response:
    return api.client.post(path, headers={"Authorization": f"Bearer {code}"})


def test_prepare_returns_only_a_claim_without_issuing_a_token(api: SetupApi) -> None:
    response = api.client.post(PREPARE, json={"harness": "codex"})
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"code"}
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", response.json()["code"])
    assert api.client.get(TOKENS).json() == []


def test_bearer_redemption_issues_a_telemetry_only_token_to_the_claim_owner(api: SetupApi, settings: AppConfig) -> None:
    code = create_claim(api)
    response = api.client.post(REDEEM, headers={
        "Authorization": f"Bearer {code}",
        "Cookie": "gateway=ignored",
        "X-Forwarded-Host": "attacker.test",
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"token", "logs_endpoint"}
    assert response.json()["logs_endpoint"] == "https://collector.example.test/otlp/v1/logs"
    assert response.json()["token"].startswith("umbod_pat_v1_")
    [metadata] = api.client.get(TOKENS).json()
    assert metadata["audience"] == "umbod:telemetry"
    assert metadata["scopes"] == ["telemetry:write"]
    assert metadata["owner"] == {
        "issuer": LOCAL_DEVELOPMENT_ISSUER,
        "subject": settings.admin_authentication.simulated_user_id,
    }


def test_wrong_harness_does_not_consume_the_claim_and_replay_fails(api: SetupApi) -> None:
    code = create_claim(api)
    wrong = redeem(api, code, REDEEM.replace("/codex/", "/claude-code/"))
    assert wrong.status_code == 401
    assert wrong.headers["cache-control"] == "no-store"
    assert redeem(api, code).status_code == 200
    replay = redeem(api, code)
    assert replay.status_code == 401
    assert replay.json() == wrong.json()


@pytest.mark.parametrize("enabled,base_url", [
    (False, "https://collector.example.test"),
    (True, ""),
    (True, "https://collector.example.test/café"),
    (True, "https://collector.example.test/%zz"),
])
def test_unavailable_telemetry_blocks_creation_and_redemption(
    api: SetupApi, settings: AppConfig, enabled: bool, base_url: str,
) -> None:
    code = create_claim(api)
    settings.otlp_receiver.enabled = enabled
    settings.endpoints.collector_base_url = base_url
    for response in (api.client.post(PREPARE, json={"harness": "codex"}), redeem(api, code)):
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"detail": "Telemetry is unavailable"}
    assert api.client.get(TOKENS).json() == []


def test_installer_is_bound_to_the_same_logs_endpoint_as_the_claim(api: SetupApi) -> None:
    response = api.client.get("/api/install/v1/codex/install.sh")
    assert response.status_code == 200
    assert "--logs-endpoint https://collector.example.test/otlp/v1/logs" in response.text.splitlines()[1]


def test_changed_logs_endpoint_rejects_redemption_without_issuing(api: SetupApi, settings: AppConfig) -> None:
    code = create_claim(api)
    settings.endpoints.collector_base_url = "https://other-collector.example.test"
    assert redeem(api, code).status_code == 401
    assert api.client.get(TOKENS).json() == []


def test_prepare_protects_cookie_requests_from_csrf(api: SetupApi) -> None:
    response = api.client.post(PREPARE, json={"harness": "codex"}, headers={"Cookie": "gateway=untrusted"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_only_the_bearer_header_is_used_not_the_query_or_body(api: SetupApi) -> None:
    code = create_claim(api)
    response = api.client.post(REDEEM, params={"code": code}, json={"code": code})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert code not in response.text
    assert redeem(api, code).status_code == 200


def test_invalid_prepare_body_does_not_echo_input(api: SetupApi) -> None:
    response = api.client.post(PREPARE, json={"harness": "sensitive-input", "code": "sensitive-code"})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Invalid install claim request"}


def test_storage_failure_does_not_echo_claim_or_exception(api: SetupApi, monkeypatch: pytest.MonkeyPatch) -> None:
    code = create_claim(api)
    with monkeypatch.context() as patch:
        patch.setattr(api.runtime.readiness, "ensure_ready", AsyncMock(side_effect=RuntimeError(code)))
        response = redeem(api, code)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert code not in response.text
    assert redeem(api, code).status_code == 200
