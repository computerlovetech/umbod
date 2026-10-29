from umbod.core.admin_overview.models import OverviewSnapshot


class InMemoryOverviewReader:
    def __init__(self, snapshot: OverviewSnapshot) -> None:
        self._snapshot = snapshot

    async def read(self) -> OverviewSnapshot:
        return self._snapshot
