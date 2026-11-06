import asyncio

import anyio
import pytest

from tests.umbod.infrastructure.connections.conftest import FakeConnectionDriver
from umbod.infrastructure.connections import (
    ConnectionProvider,
    UnpooledConnectionProvider,
)

pytestmark = pytest.mark.asyncio


async def test_each_direct_lease_owns_a_new_connection(
    driver: FakeConnectionDriver,
) -> None:
    provider: ConnectionProvider[object] = UnpooledConnectionProvider(
        driver.connect, driver.close
    )
    await provider.initialize()
    await provider.close()
    async with provider.get_connection() as first:
        assert driver.closed == []
    async with provider.get_connection() as second:
        assert second is not first
    assert driver.closed == driver.opened
    assert driver.reset_connections == []


async def test_direct_body_failure_still_closes_connection(
    driver: FakeConnectionDriver,
) -> None:
    provider = UnpooledConnectionProvider(driver.connect, driver.close)
    with pytest.raises(ValueError, match="body failed"):
        async with provider.get_connection():
            raise ValueError("body failed")
    assert driver.closed == driver.opened


async def test_direct_factory_failure_does_not_close_unowned_connection(
    driver: FakeConnectionDriver,
) -> None:
    driver.fail_connect_at = 1
    provider = UnpooledConnectionProvider(driver.connect, driver.close)
    with pytest.raises(RuntimeError, match="connect failed"):
        async with provider.get_connection():
            pytest.fail("Factory failure must prevent entry")
    assert driver.closed == []


async def test_direct_release_completes_under_anyio_cancellation(
    driver: FakeConnectionDriver,
) -> None:
    provider = UnpooledConnectionProvider(driver.connect, driver.close)
    with anyio.CancelScope() as scope:
        async with provider.get_connection():
            scope.cancel()
            await anyio.lowlevel.checkpoint()
    assert len(driver.closed) == 1
    assert driver.closed == driver.opened


async def test_direct_closer_failure_propagates(driver: FakeConnectionDriver) -> None:
    driver.fail_close = True
    provider = UnpooledConnectionProvider(driver.connect, driver.close)
    with pytest.raises(RuntimeError, match="close failed"):
        async with provider.get_connection():
            await asyncio.sleep(0)
