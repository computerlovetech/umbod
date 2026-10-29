import asyncio
from collections.abc import Awaitable, Callable

import pytest

from umbod.core.icons import (
    FaviconDiscovery,
    FaviconDiscoveryRequest,
    FaviconDiscoveryStrategy,
    FaviconDiscoveryTimedOut,
    FaviconFound,
    FaviconNotFound,
    StrategyFaviconDiscovery,
)
from tests.support.icons import InMemoryFaviconDiscoveryStrategy


class FunctionStrategy:
    def __init__(
        self,
        operation: Callable[
            [FaviconDiscoveryRequest], Awaitable[FaviconFound | FaviconNotFound]
        ],
    ) -> None:
        self._operation = operation

    async def discover(
        self, discovery_request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound:
        return await self._operation(discovery_request)


class ControlledStrategy:
    def __init__(self, result: FaviconFound | FaviconNotFound) -> None:
        self.result = result
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def discover(
        self, discovery_request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound:
        self.started.set()
        try:
            await self.release.wait()
            return self.result
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.cleaned.set()


def discovery(
    batches: tuple[tuple[FaviconDiscoveryStrategy, ...], ...],
) -> FaviconDiscovery:
    return StrategyFaviconDiscovery(
        batches=batches,
        strategy_timeout_seconds=10.0,
        overall_timeout_seconds=20.0,
    )


@pytest.mark.asyncio
async def test_sequential_order_stops_at_first_hit(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    calls: list[str] = []

    def strategy(
        name: str, result: FaviconFound | FaviconNotFound
    ) -> FaviconDiscoveryStrategy:
        memory: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy(
            {str(discovery_request.endpoint_url): result}
        )

        async def discover_request(
            incoming: FaviconDiscoveryRequest,
        ) -> FaviconFound | FaviconNotFound:
            calls.append(name)
            return await memory.discover(incoming)

        return FunctionStrategy(discover_request)

    service = discovery(
        (
            (strategy("miss", FaviconNotFound()),),
            (strategy("hit", found),),
            (strategy("unused", found),),
        )
    )

    assert await service.discover(discovery_request) == found
    assert calls == ["miss", "hit"]


@pytest.mark.parametrize("batches", [(), ((),)])
@pytest.mark.asyncio
async def test_empty_configuration_returns_not_found(
    discovery_request: FaviconDiscoveryRequest,
    batches: tuple[tuple[FaviconDiscoveryStrategy, ...], ...],
) -> None:
    service = discovery(batches)

    assert await service.discover(discovery_request) == FaviconNotFound()


@pytest.mark.asyncio
async def test_all_misses_return_not_found(
    discovery_request: FaviconDiscoveryRequest,
) -> None:
    strategy: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy({})
    service = discovery(((strategy, strategy), (strategy,)))

    assert await service.discover(discovery_request) == FaviconNotFound()


@pytest.mark.asyncio
async def test_strategy_exception_isolated_without_logging_secrets(
    discovery_request: FaviconDiscoveryRequest,
    found: FaviconFound,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fail(incoming: FaviconDiscoveryRequest) -> FaviconFound | FaviconNotFound:
        raise RuntimeError("private-endpoint-secret")

    fallback: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy(
        {str(discovery_request.endpoint_url): found}
    )
    service = discovery(((FunctionStrategy(fail),), (fallback,)))

    assert await service.discover(discovery_request) == found
    assert len(caplog.records) == 1
    assert caplog.records[0].exception_type == "RuntimeError"
    assert caplog.records[0].strategy_type == "FunctionStrategy"
    assert "private-endpoint-secret" not in caplog.text
    assert str(discovery_request.endpoint_url) not in caplog.text
    assert caplog.records[0].exc_info is None


@pytest.mark.asyncio
async def test_strategy_timeout_awaits_cleanup_then_tries_next(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    blocked = ControlledStrategy(FaviconNotFound())
    fallback: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy(
        {str(discovery_request.endpoint_url): found}
    )
    service: FaviconDiscovery = StrategyFaviconDiscovery(
        batches=((blocked,), (fallback,)),
        strategy_timeout_seconds=0.01,
        overall_timeout_seconds=10.0,
    )

    assert await service.discover(discovery_request) == found
    assert blocked.cancelled.is_set()
    assert blocked.cleaned.is_set()


@pytest.mark.asyncio
async def test_concurrent_miss_does_not_beat_later_hit(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    hit = ControlledStrategy(found)
    missed = asyncio.Event()

    async def miss(incoming: FaviconDiscoveryRequest) -> FaviconFound | FaviconNotFound:
        await hit.started.wait()
        missed.set()
        return FaviconNotFound()

    service = discovery(((FunctionStrategy(miss), hit),))
    task = asyncio.create_task(service.discover(discovery_request))
    await missed.wait()
    assert not task.done()
    hit.release.set()

    assert await task == found


@pytest.mark.asyncio
async def test_later_batch_waits_for_all_previous_misses(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    first = ControlledStrategy(FaviconNotFound())
    second = ControlledStrategy(FaviconNotFound())
    later = ControlledStrategy(found)
    service = discovery(((first, second), (later,)))
    task = asyncio.create_task(service.discover(discovery_request))
    await asyncio.gather(first.started.wait(), second.started.wait())
    first.release.set()
    await first.cleaned.wait()
    assert not later.started.is_set()
    second.release.set()
    await later.started.wait()
    later.release.set()

    assert await task == found


@pytest.mark.asyncio
async def test_first_completed_hit_wins_and_awaits_loser_cleanup(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    loser = ControlledStrategy(found.model_copy(update={"strategy": "slow"}))
    winner = ControlledStrategy(found)
    service = discovery(((loser, winner),))
    task = asyncio.create_task(service.discover(discovery_request))
    await asyncio.gather(loser.started.wait(), winner.started.wait())
    winner.release.set()

    assert await task == found
    assert loser.cancelled.is_set()
    assert loser.cleaned.is_set()


@pytest.mark.asyncio
async def test_simultaneous_hits_resolve_in_configuration_order(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    first = ControlledStrategy(found)
    second = ControlledStrategy(found.model_copy(update={"strategy": "second"}))
    service = discovery(((first, second),))
    task = asyncio.create_task(service.discover(discovery_request))
    await asyncio.gather(first.started.wait(), second.started.wait())
    second.release.set()
    first.release.set()

    assert await task == found
    assert first.cleaned.is_set()
    assert second.cleaned.is_set()


@pytest.mark.asyncio
async def test_overall_deadline_cancels_and_awaits_all_strategies(
    discovery_request: FaviconDiscoveryRequest,
) -> None:
    strategies = (
        ControlledStrategy(FaviconNotFound()),
        ControlledStrategy(FaviconNotFound()),
    )
    service: FaviconDiscovery = StrategyFaviconDiscovery(
        batches=(strategies,),
        strategy_timeout_seconds=10.0,
        overall_timeout_seconds=0.01,
    )

    assert await service.discover(discovery_request) == FaviconDiscoveryTimedOut()
    assert all(strategy.cancelled.is_set() for strategy in strategies)
    assert all(strategy.cleaned.is_set() for strategy in strategies)


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_after_all_cleanup(
    discovery_request: FaviconDiscoveryRequest,
) -> None:
    strategies = (
        ControlledStrategy(FaviconNotFound()),
        ControlledStrategy(FaviconNotFound()),
    )
    service = discovery((strategies,))
    task = asyncio.create_task(service.discover(discovery_request))
    await asyncio.gather(*(strategy.started.wait() for strategy in strategies))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(strategy.cancelled.is_set() for strategy in strategies)
    assert all(strategy.cleaned.is_set() for strategy in strategies)


@pytest.mark.parametrize("completion", ["win", "deadline", "caller"])
@pytest.mark.asyncio
async def test_discovery_waits_for_asynchronous_cancellation_cleanup(
    discovery_request: FaviconDiscoveryRequest,
    found: FaviconFound,
    completion: str,
) -> None:
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def blocked(
        incoming: FaviconDiscoveryRequest,
    ) -> FaviconFound | FaviconNotFound:
        started.set()
        try:
            await asyncio.Event().wait()
            return FaviconNotFound()
        finally:
            cleanup_started.set()
            await cleanup_release.wait()
            cleanup_finished.set()

    winner = ControlledStrategy(found)
    strategies: tuple[FaviconDiscoveryStrategy, ...] = (FunctionStrategy(blocked),)
    if completion == "win":
        strategies += (winner,)
    service: FaviconDiscovery = StrategyFaviconDiscovery(
        batches=(strategies,),
        strategy_timeout_seconds=10.0,
        overall_timeout_seconds=0.01 if completion == "deadline" else 20.0,
    )
    task = asyncio.create_task(service.discover(discovery_request))
    await started.wait()
    if completion == "win":
        await winner.started.wait()
        winner.release.set()
    elif completion == "caller":
        task.cancel()
    await cleanup_started.wait()
    assert not task.done()
    cleanup_release.set()

    if completion == "caller":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        expected = found if completion == "win" else FaviconDiscoveryTimedOut()
        assert await task == expected
    assert cleanup_finished.is_set()


@pytest.mark.parametrize(
    "invalid", [0.0, -1.0, float("nan"), float("inf"), -float("inf")]
)
@pytest.mark.parametrize(
    "field", ["strategy_timeout_seconds", "overall_timeout_seconds"]
)
def test_timeouts_must_be_positive_and_finite(invalid: float, field: str) -> None:
    timeouts = {"strategy_timeout_seconds": 1.0, "overall_timeout_seconds": 1.0}
    timeouts[field] = invalid

    with pytest.raises(ValueError, match=field):
        StrategyFaviconDiscovery(batches=(), **timeouts)
