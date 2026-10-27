from .models import AdminOverview, AttentionCounts, Available, ConnectorCounts, ToolCounts, Unavailable
from .ports import OverviewReader


class AdminOverviewService:
    def __init__(self, reader: OverviewReader) -> None:
        self._reader = reader

    async def read(self) -> AdminOverview:
        snapshot = await self._reader.read()
        connectors = tuple(
            row.connectors.value
            for row in snapshot.breakdown
            if isinstance(row.connectors, Available)
        )
        tools = tuple(
            row.tools.value
            for row in snapshot.breakdown
            if isinstance(row.tools, Available)
        )
        complete_connectors = len(connectors) == len(snapshot.breakdown)
        complete_tools = len(tools) == len(snapshot.breakdown)
        return AdminOverview(
            breakdown=snapshot.breakdown,
            permission_groups=snapshot.permission_groups,
            configured=Available(status="available", value=sum(row.configured for row in connectors))
            if complete_connectors else Unavailable(status="unavailable"),
            published=Available(status="available", value=sum(row.published for row in connectors))
            if complete_connectors else Unavailable(status="unavailable"),
            tools=Available(
                status="available",
                value=ToolCounts(
                    enabled=sum(row.enabled for row in tools),
                    known=sum(row.known for row in tools),
                ),
            ) if complete_tools else Unavailable(status="unavailable"),
            attention=_attention(connectors)
            if complete_connectors else Unavailable(status="unavailable"),
        )


def _attention(connectors: tuple[ConnectorCounts, ...]) -> Available[AttentionCounts]:
    return Available(
        status="available",
        value=AttentionCounts(
            unconfigured=sum(row.unconfigured for row in connectors),
            draft=sum(row.draft for row in connectors),
            unpublished=sum(row.unpublished for row in connectors),
            unhealthy=sum(row.unhealthy for row in connectors),
        ),
    )
