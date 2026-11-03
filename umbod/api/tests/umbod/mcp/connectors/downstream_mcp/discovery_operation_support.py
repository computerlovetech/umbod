from datetime import UTC, datetime
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions

from umbod.core.connectors.downstream_mcp.personal_connections.caller import UnavailablePersonalCaller
from umbod.core.connectors.downstream_mcp.personal_tools.models import PersonalToolDiscoveryQuery, PersonalToolRecord
from umbod.mcp.connectors.downstream_mcp.permissions import DownstreamToolPermissionPolicySource, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp.personal_discovery import PersonalDiscoveryOperations
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime


class UnavailableCallers:
    async def get_caller(self) -> UnavailablePersonalCaller:
        return UnavailablePersonalCaller(kind="unavailable")


class RejectingDiscoveryReader:
    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        raise AssertionError("Private discovery must not be read")


def empty_personal_discovery(runtime: DownstreamDiscoveryRuntime) -> PersonalDiscoveryOperations:
    return personal_discovery_with_policy(runtime, UnrestrictedDownstreamToolPermissionPolicy())


def personal_discovery_with_policy(runtime: DownstreamDiscoveryRuntime, permission_policy: DownstreamToolPermissionPolicySource) -> PersonalDiscoveryOperations:
    return PersonalDiscoveryOperations(runtime, UnavailableCallers(), RejectingDiscoveryReader(), InMemoryGroupConnectorToolPermissions(group_claim_fields=()), lambda: datetime.now(UTC), permission_policy)
