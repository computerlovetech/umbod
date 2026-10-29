import pytest

from umbod.core.admin_overview import AdminOverviewService, OverviewReader
from tests.support.admin_overview import InMemoryOverviewReader
from umbod.core.admin_overview.models import (
    AttentionCounts,
    Available,
    ConnectorCounts,
    OverviewBreakdown,
    OverviewSnapshot,
    ToolCounts,
    Unavailable,
)


pytestmark = pytest.mark.asyncio


@pytest.fixture
def snapshot() -> OverviewSnapshot:
    return OverviewSnapshot(
        breakdown=(
            OverviewBreakdown(
                kind="catalog",
                connectors=Available(status="available", value=ConnectorCounts(
                    configured=2, published=1, unconfigured=1, draft=1, unpublished=0, unhealthy=0,
                )),
                tools=Available(status="available", value=ToolCounts(enabled=2, known=4)),
            ),
            OverviewBreakdown(
                kind="openapi",
                connectors=Available(status="available", value=ConnectorCounts(
                    configured=1, published=0, unconfigured=0, draft=0, unpublished=1, unhealthy=0,
                )),
                tools=Available(status="available", value=ToolCounts(enabled=1, known=3)),
            ),
            OverviewBreakdown(
                kind="mcp",
                connectors=Available(status="available", value=ConnectorCounts(
                    configured=2, published=1, unconfigured=0, draft=1, unpublished=0, unhealthy=1,
                )),
                tools=Available(status="available", value=ToolCounts(enabled=0, known=2)),
            ),
        ),
        permission_groups=Available(status="available", value=3),
    )


async def test_sums_available_families(snapshot: OverviewSnapshot) -> None:
    reader: OverviewReader = InMemoryOverviewReader(snapshot)
    result = await AdminOverviewService(reader).read()
    assert result.configured == Available(status="available", value=5)
    assert result.published == Available(status="available", value=2)
    assert result.tools == Available(status="available", value=ToolCounts(enabled=3, known=9))
    assert result.attention == Available(status="available", value=AttentionCounts(
        unconfigured=1, draft=2, unpublished=1, unhealthy=1,
    ))
    assert result.permission_groups == snapshot.permission_groups


async def test_unavailable_tools_preserve_connector_counts(snapshot: OverviewSnapshot) -> None:
    first, second, third = snapshot.breakdown
    changed = snapshot.model_copy(update={"breakdown": (
        first.model_copy(update={"tools": Unavailable(status="unavailable")}), second, third,
    )})
    result = await AdminOverviewService(InMemoryOverviewReader(changed)).read()
    assert result.tools == Unavailable(status="unavailable")
    assert result.configured == Available(status="available", value=5)
    assert result.breakdown[1:] == snapshot.breakdown[1:]


async def test_unavailable_connectors_do_not_report_incomplete_totals(snapshot: OverviewSnapshot) -> None:
    first, second, third = snapshot.breakdown
    changed = snapshot.model_copy(update={"breakdown": (
        first, second.model_copy(update={"connectors": Unavailable(status="unavailable")}), third,
    )})
    result = await AdminOverviewService(InMemoryOverviewReader(changed)).read()
    assert result.configured == Unavailable(status="unavailable")
    assert result.published == Unavailable(status="unavailable")
    assert result.attention == Unavailable(status="unavailable")
    assert result.permission_groups == snapshot.permission_groups


async def test_permission_failure_preserves_connector_and_tool_totals(snapshot: OverviewSnapshot) -> None:
    changed = snapshot.model_copy(update={"permission_groups": Unavailable(status="unavailable")})
    result = await AdminOverviewService(InMemoryOverviewReader(changed)).read()
    assert result.permission_groups == Unavailable(status="unavailable")
    assert result.configured == Available(status="available", value=5)
    assert result.tools == Available(status="available", value=ToolCounts(enabled=3, known=9))
