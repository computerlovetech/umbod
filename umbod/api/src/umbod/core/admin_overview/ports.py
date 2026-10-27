from typing import Protocol

from .models import OverviewSnapshot


class OverviewReader(Protocol):
    async def read(self) -> OverviewSnapshot: ...
