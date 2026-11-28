from umbod.core.persistence import Database

from .errors import UnregisteredMappingGroups
from .models import (
    EffectiveProviderGroupMappings,
    ProviderGroupMapping,
    ProviderGroupMappings,
)
from .service import ProviderGroupMappingsService
from .store import (
    DatabaseProviderGroupMappingsStore,
    read_saved_provider_group_mappings,
)

__all__ = [
    "EffectiveProviderGroupMappings",
    "ProviderGroupMapping",
    "ProviderGroupMappings",
    "ProviderGroupMappingsService",
    "UnregisteredMappingGroups",
    "create_provider_group_mappings_service",
    "read_saved_provider_group_mappings",
]


def create_provider_group_mappings_service(
    database: Database,
) -> ProviderGroupMappingsService:
    return ProviderGroupMappingsService(DatabaseProviderGroupMappingsStore(database))
