import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Protocol

from messaging.models import StreamEvent
from messaging.ports import EventCheckpointStore

logger = logging.getLogger(__name__)


class ProjectionEventReader(Protocol):
    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]: ...


class RuntimeProjectionHealth:
    def __init__(self) -> None:
        self.ready = False
        self.last_applied_sequence = 0
        self.failed = False


class RuntimeProjectionSynchronizer:
    def __init__(
        self,
        reader: ProjectionEventReader,
        checkpoints: EventCheckpointStore,
        reconcile: Callable[[], Awaitable[None]],
        health: RuntimeProjectionHealth,
        interval_seconds: float,
        batch_limit: int,
    ) -> None:
        self._reader = reader
        self._checkpoints = checkpoints
        self._reconcile = reconcile
        self._health = health
        self._interval_seconds = interval_seconds
        self._batch_limit = batch_limit
        self._consumer_id = f'mcp-runtime-{secrets.token_hex(16)}'
        self._stopped = asyncio.Event()
        self._reconciliation = asyncio.Lock()

    async def bootstrap(self) -> None:
        async with self._reconciliation:
            self._health.ready = False
            try:
                sequence = await self._checkpoints.get_last_processed_sequence(self._consumer_id)
                events = await self._reader.list_after(sequence, self._batch_limit)
                while events:
                    sequence = events[-1].sequence
                    events = await self._reader.list_after(sequence, self._batch_limit)
                await self._apply(mark_ready=False)
                await self._checkpoints.save_last_processed_sequence(self._consumer_id, sequence)
                self._health.last_applied_sequence = sequence
                while await self._poll_once(mark_ready=False):
                    pass
            except Exception:
                self._health.failed = True
                raise
            self._health.ready = True

    async def _apply(self, mark_ready: bool) -> None:
        try:
            await self._reconcile()
        except Exception as error:
            self._health.ready = False
            self._health.failed = True
            logger.error('MCP runtime projection reconciliation failed', extra={'exception_type': type(error).__name__})
            raise
        self._health.failed = False
        self._health.ready = mark_ready

    async def poll_once(self) -> bool:
        async with self._reconciliation:
            return await self._poll_once(mark_ready=True)

    async def _poll_once(self, mark_ready: bool) -> bool:
        try:
            sequence = await self._checkpoints.get_last_processed_sequence(self._consumer_id)
            events = await self._reader.list_after(sequence, self._batch_limit)
            if not events:
                if self._health.failed:
                    await self._apply(mark_ready)
                return False
            await self._apply(mark_ready)
            sequence = events[-1].sequence
            await self._checkpoints.save_last_processed_sequence(self._consumer_id, sequence)
            self._health.last_applied_sequence = sequence
            return True
        except Exception:
            self._health.ready = False
            self._health.failed = True
            raise

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                if await self.poll_once():
                    continue
            except Exception as error:
                logger.error('MCP runtime event delivery failed; retrying without advancing checkpoint', extra={'exception_type': type(error).__name__, 'last_applied_sequence': self._health.last_applied_sequence})
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()
