from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryQuery, PersonalToolRecord
from umbod.core.connectors.downstream_mcp.stores.factory import DownstreamMcpStores


async def read_available(bundle: DownstreamMcpStores, query: PersonalRuntimeAuthorizationQuery) -> tuple[PersonalToolRecord, ...]:
    definitions = (await bundle.definitions.list()).definitions
    return await bundle.personal_tool_discovery.read(PersonalToolDiscoveryQuery(principal=query.key.principal, definitions=definitions, now=query.now))
