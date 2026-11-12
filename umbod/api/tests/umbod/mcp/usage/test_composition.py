from datetime import datetime, timezone

import pytest
from fastmcp import Client

from tests.mcp_fixtures import build_test_mcp
from umbod.config import AppConfig
from umbod.config.usage import PersonalUsageConfig
from umbod.core.usage.models import OwnedUsageQuery, UsageOwner
from umbod.core.usage.store import DatabaseUsageStore
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter
from umbod.mcp.signals.events import (
    McpInteractionType, McpInvocationActor, McpToolIdentity,
    McpToolInvocationStarted, McpToolInvocationSucceeded,
)


@pytest.mark.asyncio
async def test_inprocess_client_starts_worker_and_flushes_real_completion_receivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppConfig(personal_usage=PersonalUsageConfig(flush_interval_seconds=0.001))
    server = await build_test_mcp(settings=settings, connector_registrations=[])
    actor = McpInvocationActor(usage_owner=UsageOwner(kind='owned', owner_id='a' * 64))
    monkeypatch.setattr(McpAuditIdentityAdapter, 'invocation_actor', lambda self, context: actor)

    @server.resource('test://usage')
    def usage_resource() -> str:
        return 'SECRET result'

    @server.prompt()
    def usage_prompt() -> str:
        return 'SECRET prompt'

    try:
        assert not server.usage_runtime.running
        assert server.invocation_signals.invocation_completed.is_connected('mcp.invocation.usage')
        assert server.invocation_signals.capability_completed.is_connected('mcp.capability.usage')
        async with Client(server) as client:
            assert server.usage_runtime.running
            await client.list_resources()
            await client.list_prompts()
            await client.read_resource('test://usage')
            await client.get_prompt('usage_prompt')
            server.invocation_signals.invocation_completed.send(McpToolInvocationSucceeded(
                McpToolInvocationStarted(McpInteractionType.TOOL_INVOCATION,
                                         McpToolIdentity('built_in', None, None), actor,
                                         int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)), 2,
            ))
        assert not server.usage_runtime.running
        summary = await DatabaseUsageStore(server.persistence_runtime.database).count_usage(
            OwnedUsageQuery(owner_id='a' * 64, days=7, as_of=datetime.now(timezone.utc)),
        )
        assert summary.totals.tool.success == 1
        assert summary.totals.resource.success == 1
        assert summary.totals.prompt.success == 1
        assert server.usage_runtime.statistics.persisted == 3
    finally:
        await server.usage_runtime.stop()
        await server.persistence_runtime.shutdown()


@pytest.mark.asyncio
async def test_disabled_public_composition_has_no_usage_receivers_or_worker() -> None:
    server = await build_test_mcp(settings=AppConfig(personal_usage=PersonalUsageConfig(enabled=False)),
                                  connector_registrations=[])
    try:
        assert not server.invocation_signals.invocation_completed.is_connected('mcp.invocation.usage')
        assert not server.invocation_signals.capability_completed.is_connected('mcp.capability.usage')
        async with Client(server):
            assert not server.usage_runtime.running
    finally:
        await server.persistence_runtime.shutdown()
