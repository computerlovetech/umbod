from datetime import timedelta

import pytest

from umbod.rest.activity.models import ActivityOverviewResponse

from .conftest import BASE, NOW, ActivityApi


@pytest.mark.parametrize(("days", "tool_successes"), [(7, 1), (30, 2)])
def test_mcp_summary_reports_owner_counts_and_ranked_tools_for_supported_windows(
    api: ActivityApi, days: int, tool_successes: int,
) -> None:
    response = api.client.get(BASE, params={"days": days}, headers=api.headers("alice"))

    assert response.status_code == 200
    overview = ActivityOverviewResponse.model_validate(response.json())
    assert overview.mcp.status == "available"
    summary = overview.mcp.summary
    assert summary.as_of == NOW
    assert summary.range.timezone == "UTC"
    end = NOW.date() + timedelta(days=1)
    start = end - timedelta(days=days)
    assert (summary.range.start, summary.range.end) == (start, end)
    assert [day.date for day in summary.daily] == [start + timedelta(days=offset) for offset in range(days)]
    assert summary.totals.tool.success == tool_successes
    assert summary.totals.resource.failure == 1
    assert summary.totals.prompt.cancelled == 1
    assert summary.totals.total == tool_successes + 2
    expected_daily_totals = {NOW.date(): 3, NOW.date() - timedelta(days=10): 1}
    assert [day.counts.total for day in summary.daily] == [
        expected_daily_totals.get(day.date, 0) for day in summary.daily
    ]
    assert len(summary.top_tools) == 1
    tool = summary.top_tools[0]
    assert (tool.count, tool.tool_name, tool.connector_name) == (tool_successes, "Files", "Umbod")
