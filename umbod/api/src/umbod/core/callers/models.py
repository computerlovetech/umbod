from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from umbod.proxies import Model


class AuthenticationProvenance(StrEnum):
    UPSTREAM_VERIFIED = "upstream_verified"
    DEPLOYMENT_AUTHENTICATED = "deployment_authenticated"
    LOCAL_SIMULATION = "local_simulation"
    LOCAL_SEMANTIC = "local_semantic"
    LOCAL_TEST = "local_test"
    AGENT_CREDENTIAL = "agent_credential"
    UNAVAILABLE = "unavailable"


class DeclaredIssuer(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


class UnavailableIssuer(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unavailable"]


class SubjectIdentity(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: DeclaredIssuer | UnavailableIssuer
    subject: str


class UnavailableSubject(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unavailable"]


class GroupMembership(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_ids: tuple[str, ...]


class CallerContext(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authentication: AuthenticationProvenance
    subject: SubjectIdentity | UnavailableSubject

    @model_validator(mode="after")
    def validate_authentication(self) -> Self:
        if self.authentication in {
            AuthenticationProvenance.AGENT_CREDENTIAL,
            AuthenticationProvenance.UNAVAILABLE,
        } and isinstance(self.subject, SubjectIdentity):
            raise ValueError("Authentication provenance cannot establish a human subject")
        return self


class CallerSnapshot(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    caller: CallerContext
    groups: GroupMembership
