import asyncio
from datetime import datetime, timedelta, timezone

from umbod.core.diagnostics import ApplicationFailureKind
from umbod.core.usage.models import UsageBatch, UsageRecord
from umbod.core.usage.otel import serialize_usage_otel
from umbod.core.usage.ports import UsageWriter

from .ports import MonotonicClock, NanosecondClock, UsageCollectionSettings, UsageSleeper
from .statistics import UsageDropReason, UsageObservations, UsageStatistics


class UsageWriteBehind:
    def __init__(
        self, settings: UsageCollectionSettings, writer: UsageWriter,
        observations: UsageObservations, monotonic: MonotonicClock,
        clock: NanosecondClock, sleep: UsageSleeper,
    ) -> None:
        self._settings = settings
        self._writer = writer
        self._observations = observations
        self._monotonic = monotonic
        self._clock = clock
        self._sleep = sleep
        self._queue: asyncio.Queue[UsageRecord] = asyncio.Queue(maxsize=settings.queue_capacity)
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False
        self._inflight: list[UsageRecord] = []
        self._next_prune = 0.0

    @property
    def statistics(self) -> UsageStatistics:
        return self._observations.statistics

    @property
    def running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    def start(self) -> None:
        if self.running or not self._settings.enabled:
            return
        self._accepting = True
        self._next_prune = self._monotonic()
        self._worker = asyncio.create_task(self._run(), name='mcp-usage-writer')

    def enqueue(self, record: UsageRecord) -> None:
        if not self._accepting:
            self._observations.drop(UsageDropReason.SHUTDOWN, 1)
            return
        try:
            size = len(serialize_usage_otel(record).encode('utf-8'))
        except Exception:
            self.projection_failed()
            return
        if size > self._settings.max_record_bytes:
            self._observations.drop(UsageDropReason.OVERSIZED, 1)
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self._observations.drop(UsageDropReason.OVERFLOW, 1)
            return
        self._observations.accept()

    def projection_failed(self) -> None:
        self._observations.drop(UsageDropReason.PROJECTION, 1)

    async def stop(self) -> None:
        self._accepting = False
        worker = self._worker
        if worker is None:
            return
        budget = self._settings.shutdown_timeout_seconds
        deadline = asyncio.get_running_loop().time() + budget
        drain_budget = budget - min(1.0, budget / 2)
        try:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=drain_budget)
            except TimeoutError:
                pass
            finally:
                worker.cancel()
                async with asyncio.timeout_at(deadline):
                    results = await asyncio.gather(worker, return_exceptions=True)
                    failure = results[0]
                    if isinstance(failure, Exception):
                        raise failure
        finally:
            if worker.done():
                self._worker = None
                count = 0
                while not self._queue.empty():
                    self._queue.get_nowait()
                    self._queue.task_done()
                    count += 1
                self._observations.drop(UsageDropReason.SHUTDOWN, count)

    async def _run(self) -> None:
        try:
            while True:
                await self._prune_if_due()
                try:
                    async with asyncio.timeout(self._settings.flush_interval_seconds):
                        first = await self._queue.get()
                except TimeoutError:
                    continue
                self._inflight.append(first)
                deadline = self._monotonic() + self._settings.flush_interval_seconds
                while len(self._inflight) < self._settings.batch_size:
                    remaining = deadline - self._monotonic()
                    if remaining <= 0:
                        break
                    try:
                        record = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        try:
                            async with asyncio.timeout(remaining):
                                record = await self._queue.get()
                        except TimeoutError:
                            break
                    self._inflight.append(record)
                persisted = await self._write(UsageBatch(records=tuple(self._inflight)))
                if persisted:
                    self._observations.persist(len(self._inflight))
                else:
                    self._observations.drop(UsageDropReason.WRITE, len(self._inflight))
                self._finish_inflight()
        finally:
            self._observations.drop(UsageDropReason.SHUTDOWN, len(self._inflight))
            self._finish_inflight()

    def _finish_inflight(self) -> None:
        for _ in self._inflight:
            self._queue.task_done()
        self._inflight.clear()

    async def _write(self, batch: UsageBatch) -> bool:
        for attempt in range(self._settings.max_retries + 1):
            try:
                async with asyncio.timeout(self._settings.write_timeout_seconds):
                    await self._writer.append_usage(batch)
                return True
            except Exception:
                if attempt < self._settings.max_retries:
                    await self._sleep(0.25 * 4**attempt)
        return False

    async def _prune_if_due(self) -> None:
        now = self._monotonic()
        if now < self._next_prune:
            return
        self._next_prune = now + 86400
        today = datetime.fromtimestamp(self._clock() / 1_000_000_000, tz=timezone.utc).date()
        before = today - timedelta(days=self._settings.retention_days - 1)
        try:
            async with asyncio.timeout(self._settings.write_timeout_seconds):
                await self._writer.prune_usage(before)
        except Exception:
            self._observations.failure(ApplicationFailureKind.USAGE_RETENTION)
