from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic_monty import AsyncMonty

from umbod.core.connectors.portable.draft_validation.ports import DraftSourceValidator

from .draft_validator import MontyDraftSourceValidator
from .sandbox import MontyPortableSandbox, portable_sdk_mount


__all__ = ["MontyDraftSourceValidator", "MontyPortableSandbox", "open_portable_draft_validator", "portable_sdk_mount"]


@asynccontextmanager
async def open_portable_draft_validator(
    *, max_processes: int, deadline_seconds: float,
) -> AsyncIterator[DraftSourceValidator]:
    with portable_sdk_mount() as mount:
        async with AsyncMonty(max_processes=max_processes) as pool:
            yield MontyDraftSourceValidator(pool, mount, deadline_seconds)
