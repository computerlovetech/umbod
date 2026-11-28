from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .models import AgentCredentialMetadata, StoredAgentCredential


class AgentCredentialClock(Protocol):
    def now(self) -> datetime: ...


class AgentCredentialGenerator(Protocol):
    def generate_id(self) -> UUID: ...

    def generate_secret(self, size: int) -> bytes: ...


class AgentCredentialStore(Protocol):
    async def insert(self, record: StoredAgentCredential) -> bool: ...

    async def find(self, agent_id: str) -> StoredAgentCredential | None: ...

    async def list_agents(self) -> tuple[AgentCredentialMetadata, ...]: ...

    async def compare_and_replace(
        self,
        previous: StoredAgentCredential,
        build_replacement: Callable[[], StoredAgentCredential],
    ) -> bool: ...
