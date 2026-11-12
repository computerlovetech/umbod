from datetime import date
from typing import Protocol

from .models import OwnedUsageQuery, UsageBatch, UsageSummary


class UsageWriter(Protocol):
    async def append_usage(self, batch: UsageBatch) -> None: ...

    async def prune_usage(self, before: date) -> None: ...


class UsageReader(Protocol):
    async def count_usage(self, query: OwnedUsageQuery) -> UsageSummary: ...
