from typing import Protocol

from .models import DiscoverPersonalOAuthSetup, PersonalOAuthSetupDiscovery, PersonalOAuthSetupValidation, ValidatePersonalOAuthSetup
from .state import PersonalOAuthSetupBinding, CompletePersonalOAuthSetup, PersonalOAuthSetupQuery, PersonalOAuthSetupStatus, StartedPersonalOAuthSetup, StartPersonalOAuthSetup


class PersonalOAuthSetupStore(Protocol):
    async def require_current(self, binding: PersonalOAuthSetupBinding) -> None: ...

    async def get(self, query: PersonalOAuthSetupQuery) -> PersonalOAuthSetupStatus: ...

    async def start(self, command: StartPersonalOAuthSetup) -> StartedPersonalOAuthSetup: ...

    async def complete(self, command: CompletePersonalOAuthSetup) -> PersonalOAuthSetupStatus: ...


class PersonalOAuthSetupProvider(Protocol):
    async def discover(self, command: DiscoverPersonalOAuthSetup) -> PersonalOAuthSetupDiscovery: ...

    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation: ...
