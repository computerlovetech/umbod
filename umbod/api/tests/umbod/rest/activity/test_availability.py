import pytest

from umbod.core.usage import OwnedUsageQuery, UsageReader, UsageSummary
from umbod.rest.activity.deps import get_mcp_activity_usage_reader
from umbod.rest.activity.models import ActivityOverviewResponse

from .conftest import BASE, DETAIL, SESSIONS, ActivityApi


def test_overview_preserves_mcp_summary_when_harness_is_disabled(disabled_harness_api: ActivityApi) -> None:
    response = disabled_harness_api.client.get(BASE, headers=disabled_harness_api.headers("alice"))

    assert response.status_code == 200
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.harness.status == "unavailable"
    assert overview.mcp.status == "available"
    assert overview.mcp.summary.totals.tool.success == 1


def test_overview_preserves_harness_summary_when_mcp_usage_is_disabled(api: ActivityApi) -> None:
    api.settings.personal_usage.enabled = False
    response = api.client.get(BASE, headers=api.headers("alice"))

    assert response.status_code == 200
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.harness.status == "available"
    assert overview.harness.summary.outcomes.success == 2
    assert overview.mcp.status == "unavailable"


def test_mcp_readiness_failure_does_not_abort_harness_overview(api: ActivityApi, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_readiness() -> None:
        raise RuntimeError("private availability detail")

    monkeypatch.setattr(api.persistence.readiness, "ensure_ready", fail_readiness)
    response = api.client.get(BASE, headers=api.headers("alice"))

    assert response.status_code == 200
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.harness.status == "available"
    assert overview.mcp.status == "unavailable"
    assert "private availability detail" not in response.text


class UnavailableUsageReader:
    async def count_usage(self, query: OwnedUsageQuery) -> UsageSummary:
        raise RuntimeError("private storage error")


def _unavailable_usage_reader() -> UsageReader:
    return UnavailableUsageReader()


def test_mcp_usage_read_failure_does_not_abort_harness_overview(api: ActivityApi) -> None:
    api.personal_app.dependency_overrides[get_mcp_activity_usage_reader] = _unavailable_usage_reader
    response = api.client.get(BASE, headers=api.headers("alice"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.harness.status == "available"
    assert overview.mcp.status == "unavailable"
    assert "private storage error" not in response.text


def test_overview_returns_typed_unavailable_states_when_both_sources_are_disabled(
    disabled_harness_api: ActivityApi,
) -> None:
    api = disabled_harness_api
    api.settings.personal_usage.enabled = False
    headers = api.headers("alice")
    profile = api.client.get("/api/me/profile", headers=headers)
    response = api.client.get(BASE, headers=headers)

    assert profile.status_code == 200
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.harness.status == overview.mcp.status == "unavailable"
    assert overview.identity_key == profile.json()["identity_key"]


@pytest.mark.parametrize("path", [SESSIONS, DETAIL])
def test_sessions_return_503_when_harness_is_disabled(disabled_harness_api: ActivityApi, path: str) -> None:
    response = disabled_harness_api.client.get(path, headers=disabled_harness_api.headers("alice"))

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
