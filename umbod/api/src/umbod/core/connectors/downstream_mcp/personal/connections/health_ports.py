from typing import Protocol

from .health_models import PersonalAuthorizationHealth, PersonalAuthorizationHealthQuery


class PersonalAuthorizationHealthStore(Protocol):
    async def get(self, query: PersonalAuthorizationHealthQuery) -> PersonalAuthorizationHealth: ...
