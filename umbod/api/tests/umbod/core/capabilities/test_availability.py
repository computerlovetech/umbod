from dataclasses import dataclass

import pytest

from umbod.core.capabilities import (
    CapabilityActivation,
    CapabilityAvailability,
    CapabilityIdentity,
    CapabilityPermissionPolicy,
    CapabilityPublication,
    CapabilityReadiness,
)


@dataclass(frozen=True)
class AvailabilityState:
    ready: bool
    published: bool
    enabled: bool
    permitted: bool


class StubPublishingStore(CapabilityPublication):
    def __init__(self, published: bool) -> None:
        self._published = published

    async def is_published(self, identity: CapabilityIdentity) -> bool:
        return self._published


class StubActivationStore(CapabilityActivation):
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    async def is_enabled(self, identity: CapabilityIdentity) -> bool:
        return self._enabled


class StubReadiness(CapabilityReadiness):
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        return self._ready


class StubPermissionPolicy(CapabilityPermissionPolicy):
    def __init__(self, permitted: bool) -> None:
        self._permitted = permitted

    async def allows(self, identity: CapabilityIdentity) -> bool:
        return self._permitted


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(
        connector_kind="native",
        connector_id="weather",
        capability_kind="tool",
            capability_key="forecast",
    )


@pytest.mark.parametrize(
    "state,expected",
    [
        (AvailabilityState(True, True, True, True), True),
        (AvailabilityState(False, True, True, True), False),
        (AvailabilityState(True, False, True, True), False),
        (AvailabilityState(True, True, False, True), False),
        (AvailabilityState(True, True, True, False), False),
    ],
    ids=["available", "not-ready", "unpublished", "disabled", "forbidden"],
)
@pytest.mark.asyncio
async def test_capability_availability_combines_shared_gates(
    state: AvailabilityState,
    expected: bool,
) -> None:
    availability = CapabilityAvailability(
        publishing=StubPublishingStore(state.published),
        activations=StubActivationStore(state.enabled),
        readiness=StubReadiness(state.ready),
        permissions=StubPermissionPolicy(state.permitted),
    )

    assert await availability.is_available(_identity()) is expected
