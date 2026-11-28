import pytest

from umbod.rest.activity.models import ActivityOverviewResponse, ActivitySessionResponse, ActivitySessionsResponse

from .conftest import BASE, DETAIL, NOW, SESSIONS, ActivityApi


@pytest.mark.parametrize("path", [BASE, SESSIONS, DETAIL])
def test_activity_routes_require_authentication(disabled_harness_api: ActivityApi, path: str) -> None:
    response = disabled_harness_api.client.get(path)

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_activity_rejects_wrong_issuer_and_unresolved_subject(disabled_harness_api: ActivityApi) -> None:
    wrong_issuer = disabled_harness_api.client.get(BASE, headers=disabled_harness_api.headers("alice", "https://wrong.test/"))
    unresolved = disabled_harness_api.client.get(BASE, headers=disabled_harness_api.headers(""))

    assert wrong_issuer.status_code == 401
    assert unresolved.status_code == 403
    assert wrong_issuer.headers["cache-control"] == unresolved.headers["cache-control"] == "no-store"


def test_member_overview_reads_only_own_harness_and_mcp_records(api: ActivityApi) -> None:
    alice = api.client.get(BASE, headers=api.headers("alice"))
    bob = api.client.get(BASE, params={"days": 30}, headers=api.headers("bob"))

    assert (alice.status_code, bob.status_code) == (200, 200)
    assert alice.headers["cache-control"] == bob.headers["cache-control"] == "no-store"
    alice_overview = ActivityOverviewResponse.model_validate(alice.json())
    bob_overview = ActivityOverviewResponse.model_validate(bob.json())
    assert (alice_overview.period.days, bob_overview.period.days) == (7, 30)
    assert alice_overview.period.as_of == bob_overview.period.as_of == NOW
    assert alice_overview.harness.status == bob_overview.harness.status == "available"
    assert alice_overview.mcp.status == bob_overview.mcp.status == "available"
    assert alice_overview.harness.summary.outcomes.model_dump() == {"success": 2, "failure": 0, "unknown": 0}
    assert bob_overview.harness.summary.outcomes.model_dump() == {"success": 0, "failure": 1, "unknown": 0}
    assert alice_overview.mcp.summary.totals.tool.success == 1
    assert alice_overview.mcp.summary.totals.tool.failure == 0
    assert bob_overview.mcp.summary.totals.tool.success == 0
    assert bob_overview.mcp.summary.totals.tool.failure == 1
    assert bob_overview.mcp.summary.totals.total == 1
    assert api.client.get("/api/admin/overview", headers=api.headers("alice")).status_code == 403


def test_activity_is_not_an_admin_or_root_endpoint(disabled_harness_api: ActivityApi) -> None:
    api = disabled_harness_api
    admin_headers = api.headers("admin", groups=(api.settings.admin_authentication.required_membership,))
    assert api.client.get("/activity").status_code == 404
    assert api.client.get("/api/admin/activity", headers=admin_headers).status_code == 404


def test_session_list_without_search_only_returns_owned_sessions(unseeded_api: ActivityApi) -> None:
    response = unseeded_api.client.get(SESSIONS, headers=unseeded_api.headers("bob"))

    assert response.status_code == 200
    page = ActivitySessionsResponse.model_validate(response.json())
    assert [session.key.session_id for session in page.sessions] == ["bob-private"]


def test_session_list_search_pages_remain_scoped_to_verified_owner(unseeded_api: ActivityApi) -> None:
    first = unseeded_api.client.get(SESSIONS, params={"q": "alice", "limit": 1}, headers=unseeded_api.headers("alice"))
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    first_page = ActivitySessionsResponse.model_validate(first.json())
    assert [item.key.session_id for item in first_page.sessions] == ["alice/segment"]
    assert first_page.page.kind == "more"

    continuation = {"q": "alice", "limit": 1, "cursor": first_page.page.cursor}
    second = unseeded_api.client.get(SESSIONS, params=continuation, headers=unseeded_api.headers("alice"))
    assert second.status_code == 200
    second_page = ActivitySessionsResponse.model_validate(second.json())
    assert [item.key.session_id for item in second_page.sessions] == ["alice-second"]
    assert second_page.page.kind == "end"

    foreign_cursor = unseeded_api.client.get(SESSIONS, params=continuation, headers=unseeded_api.headers("bob"))
    assert foreign_cursor.status_code == 422
    assert foreign_cursor.headers["cache-control"] == "no-store"


def test_session_detail_accepts_path_session_id_without_disclosing_foreign_session(unseeded_api: ActivityApi) -> None:
    found = unseeded_api.client.get(DETAIL, headers=unseeded_api.headers("alice"))
    foreign = unseeded_api.client.get(DETAIL, headers=unseeded_api.headers("bob"))
    missing = unseeded_api.client.get(SESSIONS + "/codex/not-a-session", headers=unseeded_api.headers("bob"))

    assert found.status_code == 200
    assert ActivitySessionResponse.model_validate(found.json()).session.key.session_id == "alice/segment"
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.headers["cache-control"] == missing.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path,query", [
    (BASE, {"days": "8"}),
    (BASE, {"days": "31"}),
    (BASE, {"days": "invalid"}),
    (BASE, {"owner": "bob"}),
    (BASE, {"scope": "instance"}),
    (BASE, {"user": "bob"}),
    (BASE, {"identity_key": "from-caller"}),
    (SESSIONS, {"days": "0"}),
    (SESSIONS, {"owner_id": "bob"}),
    (SESSIONS, {"q": "x" * 129}),
    (SESSIONS, {"cursor": ""}),
    (SESSIONS, {"cursor": "x" * 16385}),
    (SESSIONS, {"cursor": "not-a-cursor"}),
    (SESSIONS, {"limit": "0"}),
    (SESSIONS, {"limit": "101"}),
    (DETAIL, {"owner": "bob"}),
    (SESSIONS + "/unsupported/session", {}),
    (SESSIONS + "/codex/", {}),
    (SESSIONS + "/codex/%20%09", {}),
    (SESSIONS + "/codex/session%00", {}),
    (SESSIONS + "/codex/" + "x" * 1025, {}),
])
def test_activity_rejects_invalid_query_and_path_values(
    disabled_harness_api: ActivityApi, path: str, query: dict[str, str],
) -> None:
    response = disabled_harness_api.client.get(path, params=query, headers=disabled_harness_api.headers("alice"))

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
