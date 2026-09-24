from umbod.core.activation.domain import ActivationStore
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.persistence import Database


async def create_capability_activation_store(database: Database) -> ActivationStore:
    return CapabilityActivationStoreService(database, CAPABILITY_ACTIVATION_STATE_TABLE)
