import pytest

from .conftest import AnalyticsHttp
from .test_routes import BASE


@pytest.mark.parametrize("token,status", [("", 401), ("member", 403), ("ingestion-token", 401)])
def test_aggregate_reads_require_administrator_credentials(
    analytics_http: AnalyticsHttp, query_body: dict[str, object], token: str, status: int,
) -> None:
    response = analytics_http.client.post(BASE, json=query_body, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert analytics_http.reader.queries == []


@pytest.mark.parametrize("headers", [
    {},
    {"Origin": "http://localhost:3010"},
    {"Origin": "https://untrusted.example", "X-Umbod-Web-Request": "1"},
])
def test_cookie_bearing_queries_require_trusted_origin_and_csrf_marker(
    analytics_http: AnalyticsHttp, query_body: dict[str, object], headers: dict[str, str],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body, headers={"Cookie": "session=present", **headers})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert analytics_http.reader.queries == []


def test_cookie_bearing_queries_with_valid_browser_headers_succeed(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body, headers={
        "Cookie": "session=present", "Origin": "http://localhost:3010", "X-Umbod-Web-Request": "1",
    })
    assert response.status_code == 200
    assert response.json()["rows"][0]["count"] == 3
