import asyncio
import logging
import math

from .models import (
    FaviconDiscoveryRequest,
    FaviconDiscoveryResult,
    FaviconDiscoveryTimedOut,
    FaviconFound,
    FaviconNotFound,
)
from .ports import FaviconDiscoveryStrategy

logger = logging.getLogger(__name__)


class StrategyFaviconDiscovery:
    def __init__(
        self,
        batches: tuple[tuple[FaviconDiscoveryStrategy, ...], ...],
        strategy_timeout_seconds: float,
        overall_timeout_seconds: float,
    ) -> None:
        for name, value in (
            ("strategy_timeout_seconds", strategy_timeout_seconds),
            ("overall_timeout_seconds", overall_timeout_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        self._batches = batches
        self._strategy_timeout_seconds = strategy_timeout_seconds
        self._overall_timeout_seconds = overall_timeout_seconds

    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconDiscoveryResult:
        try:
            async with asyncio.timeout(self._overall_timeout_seconds):
                for batch in self._batches:
                    result = await self._discover_batch(batch, request)
                    if isinstance(result, FaviconFound):
                        return result
                return FaviconNotFound()
        except TimeoutError:
            return FaviconDiscoveryTimedOut()

    async def _discover_batch(
        self,
        batch: tuple[FaviconDiscoveryStrategy, ...],
        request: FaviconDiscoveryRequest,
    ) -> FaviconFound | FaviconNotFound:
        tasks: list[asyncio.Task[FaviconFound | FaviconNotFound]] = []
        try:
            tasks = [
                asyncio.create_task(self._discover_strategy(strategy, request))
                for strategy in batch
            ]
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in tasks:
                    if task in done:
                        result = task.result()
                        if isinstance(result, FaviconFound):
                            return result
            return FaviconNotFound()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _discover_strategy(
        self,
        strategy: FaviconDiscoveryStrategy,
        request: FaviconDiscoveryRequest,
    ) -> FaviconFound | FaviconNotFound:
        try:
            async with asyncio.timeout(self._strategy_timeout_seconds):
                return await strategy.discover(request)
        except Exception as error:
            logger.warning(
                "Favicon discovery strategy failed",
                extra={
                    "strategy_type": type(strategy).__name__,
                    "exception_type": type(error).__name__,
                },
            )
            return FaviconNotFound()
