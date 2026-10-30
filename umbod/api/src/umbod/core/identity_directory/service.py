import logging

from .models import IdentityObservation
from .ports import IdentityDirectoryStore

logger = logging.getLogger(__name__)


class IdentityObservationService:
    def __init__(self, store: IdentityDirectoryStore) -> None:
        self._store = store

    async def observe_best_effort(self, observation: IdentityObservation) -> None:
        try:
            await self._store.observe(observation)
        except Exception:
            logger.warning(
                "identity_directory_observation_failed",
                extra={"event": "identity_directory_observation_failed"},
            )
