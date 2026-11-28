from typing import Literal, Protocol

from pydantic import ConfigDict

from umbod.proxies import Model
from umbod.core.callers import AuthenticationProvenance, CallerContext, GroupMembership

from .models import CanonicalPrincipal, MissingCanonicalPrincipal


class PersonalCaller(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    caller: CallerContext
    principal: CanonicalPrincipal
    groups: GroupMembership


class UnavailablePersonalCaller(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unavailable"]


class PersonalCallerProvider(Protocol):
    async def get_caller(self) -> PersonalCaller | UnavailablePersonalCaller: ...


def require_personal_caller(caller: PersonalCaller | UnavailablePersonalCaller) -> PersonalCaller:
    if isinstance(caller, UnavailablePersonalCaller) or caller.caller.authentication == AuthenticationProvenance.UNAVAILABLE:
        raise MissingCanonicalPrincipal()
    return caller
