from collections.abc import Hashable
from dataclasses import dataclass
from uuid import UUID

import pytest

from umbod.core.key_value import KeyValueDriver, KeyValueHit, KeyValueMiss
from umbod.infrastructure.key_value import create_inmemory_key_value_driver


@dataclass(frozen=True)
class CompoundKey:
    namespace: UUID
    key: tuple[str, int]


@pytest.fixture
def driver() -> KeyValueDriver[Hashable, object]:
    return create_inmemory_key_value_driver()


@pytest.mark.asyncio
async def test_missing_key_returns_explicit_miss(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    assert await driver.get("missing") == KeyValueMiss()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, False, 0, 0.0, "", [], {}, (), "value"])
async def test_stored_values_return_hits(
    driver: KeyValueDriver[Hashable, object], value: object,
) -> None:
    await driver.set("key", value)

    result = await driver.get("key")

    assert isinstance(result, KeyValueHit)
    assert result.value is value


@pytest.mark.asyncio
async def test_setting_existing_key_overwrites_value(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    await driver.set("key", "original")
    await driver.set("key", "replacement")

    assert await driver.get("key") == KeyValueHit("replacement")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        42,
        UUID(int=1),
        ("namespace", ("key", 7)),
        frozenset({"first", "second"}),
        CompoundKey(UUID(int=1), ("key", 7)),
    ],
)
async def test_hashable_keys_roundtrip(
    driver: KeyValueDriver[Hashable, object], key: Hashable,
) -> None:
    await driver.set(key, "value")

    assert await driver.get(key) == KeyValueHit("value")


@pytest.mark.asyncio
async def test_equivalent_compound_keys_resolve_same_value(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    await driver.set(CompoundKey(UUID(int=1), ("key", 7)), "value")

    assert await driver.get(CompoundKey(UUID(int=1), ("key", 7))) == KeyValueHit(
        "value"
    )


@pytest.mark.asyncio
async def test_factory_creates_isolated_storage() -> None:
    first: KeyValueDriver[str, str] = create_inmemory_key_value_driver()
    second: KeyValueDriver[str, str] = create_inmemory_key_value_driver()
    await first.set("key", "first")
    await second.set("key", "second")

    assert await first.get("key") == KeyValueHit("first")
    assert await second.get("key") == KeyValueHit("second")


@pytest.mark.asyncio
async def test_delete_removes_only_selected_key(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    await driver.set("removed", "value")
    await driver.set("retained", "value")
    await driver.delete("removed")

    assert await driver.get("removed") == KeyValueMiss()
    assert await driver.get("retained") == KeyValueHit("value")


@pytest.mark.asyncio
async def test_deleting_missing_key_is_repeatable(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    await driver.delete("missing")
    await driver.delete("missing")

    assert await driver.get("missing") == KeyValueMiss()


@pytest.mark.asyncio
async def test_clear_is_repeatable_and_scoped_to_driver_instance() -> None:
    first: KeyValueDriver[str, str] = create_inmemory_key_value_driver()
    second: KeyValueDriver[str, str] = create_inmemory_key_value_driver()
    await first.set("one", "first")
    await first.set("two", "first")
    await second.set("one", "second")
    await first.clear()
    await first.clear()

    assert await first.get("one") == KeyValueMiss()
    assert await first.get("two") == KeyValueMiss()
    assert await second.get("one") == KeyValueHit("second")


@pytest.mark.asyncio
async def test_driver_can_store_after_clear(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    await driver.set("key", "original")
    await driver.clear()
    await driver.set("key", "replacement")

    assert await driver.get("key") == KeyValueHit("replacement")


@pytest.mark.asyncio
async def test_values_remain_shared_by_reference(
    driver: KeyValueDriver[Hashable, object],
) -> None:
    value: list[str] = []
    await driver.set("key", value)
    value.append("updated")

    result = await driver.get("key")

    assert isinstance(result, KeyValueHit)
    assert result.value is value
    assert result.value == ["updated"]
