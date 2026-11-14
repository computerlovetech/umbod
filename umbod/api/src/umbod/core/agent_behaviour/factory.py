from datetime import UTC, datetime
from uuid import uuid4

from umbod.core.persistence import Database

from .service import AgentBehaviourService
from .store import DatabaseAgentBehaviourStore


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_agent_behaviour_service(database: Database) -> AgentBehaviourService:
    return AgentBehaviourService(DatabaseAgentBehaviourStore(database), utc_now, uuid4)
