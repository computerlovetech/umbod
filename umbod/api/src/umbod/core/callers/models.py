from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator


class AuthenticationProvenance(StrEnum):
    UPSTREAM_VERIFIED = "upstream_verified"
    DEPLOYMENT_AUTHENTICATED = "deployment_authenticated"
    LOCAL_SIMULATION = "local_simulation"
    LOCAL_SEMANTIC = "local_semantic"
    LOCAL_TEST = "local_test"
    UNAVAILABLE = "unavailable"


class DeclaredIssuer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


class UnavailableIssuer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unavailable"]


class SubjectIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: DeclaredIssuer | UnavailableIssuer
    subject: str


class UnavailableSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unavailable"]


class GroupMembership(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_ids: tuple[str, ...]


class CallerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authentication: AuthenticationProvenance
    subject: SubjectIdentity | UnavailableSubject

    @model_validator(mode="after")
    def validate_authentication(self) -> Self:
        if self.authentication == AuthenticationProvenance.UNAVAILABLE and isinstance(self.subject, SubjectIdentity):
            raise ValueError("Unavailable authentication cannot establish a subject")
        return self


class CallerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    caller: CallerContext
    groups: GroupMembership
