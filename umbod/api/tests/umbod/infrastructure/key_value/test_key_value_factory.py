import subprocess
import sys

import pytest

from umbod.core.caching import AsyncRequestCache
from umbod.infrastructure.key_value import create_request_cache


def test_importing_public_composition_does_not_load_concrete_key_value_driver() -> None:
    program = (
        "import sys, umbod.infrastructure; "
        "raise SystemExit('umbod.infrastructure.key_value.inmemory' in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_request_cache_factory_creates_independent_caches() -> None:
    first: AsyncRequestCache[str, str] = create_request_cache()
    second: AsyncRequestCache[str, str] = create_request_cache()

    async def load_first() -> str:
        return "first"

    async def load_second() -> str:
        return "second"

    assert await first.get_or_load("key", load_first) == "first"
    assert await second.get_or_load("key", load_second) == "second"
    assert await first.get_or_load("key", load_second) == "first"
    assert await second.get_or_load("key", load_first) == "second"
