from umbod.core.callers.membership import ProviderMembershipClaim
from umbod.core.persistence import Database

from ..ports import SettingsNotConfigured

from .errors import UnregisteredMappingGroups
from .models import (
    EffectiveProviderGroupMappings,
    ProviderGroupMapping,
    ProviderGroupMappings,
)
from .ports import ProviderGroupMappingsReader
from .service import ProviderGroupMappingsService
from .store import (
    DatabaseProviderGroupMappingsStore,
    read_saved_provider_group_mappings,
)

__all__ = [
    "EffectiveProviderGroupMappings",
    "ProviderGroupMapping",
    "ProviderGroupMappings",
    "ProviderGroupMappingsReader",
    "ProviderGroupMappingsService",
    "UnregisteredMappingGroups",
    "create_provider_group_mappings_service",
    "read_saved_provider_group_mappings",
]


def create_provider_group_mappings_service(
    database: Database,
    defaults: ProviderGroupMappingsReader,
    provider_claim: ProviderMembershipClaim | SettingsNotConfigured,
) -> ProviderGroupMappingsService:
    return ProviderGroupMappingsService(
        DatabaseProviderGroupMappingsStore(database), defaults, provider_claim
    )
