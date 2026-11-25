from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from .models import CanonicalPrincipal


class _PersonalIdentityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AbsentIssuer(_PersonalIdentityModel):
    kind: Literal["absent"]


class MalformedIssuer(_PersonalIdentityModel):
    kind: Literal["malformed"]


class DeclaredIssuer(_PersonalIdentityModel):
    value: str


class ObservedIdentityString(_PersonalIdentityModel):
    value: str


class UnavailableIdentityString(_PersonalIdentityModel):
    kind: Literal["unavailable"]


class PersonalIdentityFacts(_PersonalIdentityModel):
    issuer: AbsentIssuer | MalformedIssuer | DeclaredIssuer
    subject: ObservedIdentityString | UnavailableIdentityString
    tenant_id: ObservedIdentityString | UnavailableIdentityString
    object_id: ObservedIdentityString | UnavailableIdentityString
    delegated_scope: StrictBool
    machine: StrictBool


class PersonalIdentityPolicy(_PersonalIdentityModel):
    enabled: StrictBool
    identity_namespace: str
    authentication_mode: str
    authentication_environment: str
    runtime_profile: str
    runtime_auth: str
    provider: str
    expected_issuer: str
    expected_tenant: str
    simulated_subject: str


class PersonalIdentityRejection(str, Enum):
    FEATURE_UNAVAILABLE = "feature_unavailable"
    AUTHENTICATION_DISABLED = "authentication_disabled"
    MACHINE = "machine"
    SIMULATION_UNAVAILABLE = "simulation_unavailable"
    ISSUER = "issuer"
    TENANT = "tenant"
    DELEGATION = "delegation"
    SUBJECT = "subject"


class ResolvedPersonalIdentity(_PersonalIdentityModel):
    principal: CanonicalPrincipal


class UnresolvedPersonalIdentity(_PersonalIdentityModel):
    reason: PersonalIdentityRejection


PersonalIdentityResolution = ResolvedPersonalIdentity | UnresolvedPersonalIdentity
