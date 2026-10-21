import asyncio
import json
from pathlib import Path

import httpx

from ...models import loopback_origin


async def retire_legacy_host(directory: Path, profile: str) -> None:
    path = directory / "runtime.json"
    if not path.exists():
        return
    record = json.loads(path.read_text())
    if record.get("profile") != profile:
        raise ValueError("Legacy runtime profile does not match")
    origin = loopback_origin(record["management"])
    async with httpx.AsyncClient(
        base_url=origin,
        timeout=3,
        trust_env=False,
        headers={"Authorization": f"Bearer {record['admin_token']}"},
    ) as client:
        try:
            response = await client.post("/manage", json={"action": "health"})
        except httpx.ConnectError:
            return
        response.raise_for_status()
        health = response.json()
        if health.get("profile") != profile or health.get("pid") != record["pid"]:
            raise ValueError("Legacy runtime identity does not match")
        response = await client.post("/manage", json={"action": "shutdown"})
        response.raise_for_status()
        async with asyncio.timeout(15):
            while path.exists():
                await asyncio.sleep(0.05)

