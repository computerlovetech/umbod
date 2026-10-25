from unittest.mock import AsyncMock

import pytest

from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
from tests.umbod.core.downstream_mcp_connectors.personal_tools.runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCallerProvider, UnavailablePersonalCaller
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRuntime
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalToolRuntime

__all__ = ["runtime_case"]


@pytest.mark.asyncio
async def test_retained_runtime_recaptures_after_listing_before_execution(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    callers = AsyncMock(spec=PersonalCallerProvider)
    callers.get_caller.side_effect = [
        captured_personal_caller(runtime_case.query.key.principal, runtime_case.query.group_ids),
        UnavailablePersonalCaller(kind="unavailable"),
    ]
    runtime: PersonalToolRuntime = McpPersonalToolRuntime(
        callers, runtime_case.bundle.definitions, runtime_case.bundle.personal_tool_access,
        execution.transport, lambda: runtime_case.query.now,
    )
    assert len(await runtime.list_tools()) == 1
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime.execute(execution.command)
    assert callers.get_caller.await_count == 2
    assert execution.transport.calls == []
