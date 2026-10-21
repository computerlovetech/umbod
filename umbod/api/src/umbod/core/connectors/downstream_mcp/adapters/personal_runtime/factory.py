import ssl

import httpcore2

from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport

from .network import SystemAddressResolver
from .transport import FastMCPPersonalMcpTransport


def create_personal_mcp_transport() -> PersonalMcpTransport:
    return FastMCPPersonalMcpTransport(
        limits=PersonalRuntimeLimits(operation_timeout_seconds=30, maximum_response_bytes=1048576, maximum_total_bytes=4194304, maximum_request_bytes=1048576, maximum_tool_pages=16),
        clock=utc_clock, resolver=SystemAddressResolver(), backend_factory=httpcore2.AnyIOBackend,
        ssl_context=ssl.create_default_context(),
    )
