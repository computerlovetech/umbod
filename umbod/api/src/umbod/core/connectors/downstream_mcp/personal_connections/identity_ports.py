from typing import Protocol

from .identity_models import PersonalIdentityFacts, PersonalIdentityPolicy, PersonalIdentityResolution


class PersonalIdentityResolver(Protocol):
    def __call__(self, policy: PersonalIdentityPolicy, facts: PersonalIdentityFacts) -> PersonalIdentityResolution: ...
