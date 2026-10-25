from collections.abc import Mapping

from umbod.config.app import AppConfig
from umbod.core.callers import GroupMembership

from ..personal_connections.development_identity import local_personal_identity_enabled
from ..personal_connections.development_identity_models import SimulatedUserIdentity
from ..personal_connections.identity_models import (
    AbsentIssuer, DeclaredIssuer, MalformedIssuer, ObservedIdentityString,
    PersonalIdentityFacts, PersonalIdentityPolicy, UnavailableIdentityString,
)


def observed_identity_string(value: object) -> ObservedIdentityString | UnavailableIdentityString:
    if isinstance(value, str) and value.strip():
        return ObservedIdentityString(value=value)
    return UnavailableIdentityString(kind="unavailable")


def machine_identity(claims: Mapping[str, object]) -> bool:
    subject = claims.get("sub")
    email = claims.get("email")
    return (
        claims.get("idtyp") == "app"
        or claims.get("gty") in ("client-credentials", "client_credentials")
        or claims.get("grant_type") == "client_credentials"
        or isinstance(subject, str) and subject.endswith("@clients")
        or isinstance(email, str) and email.endswith(".gserviceaccount.com")
    )


def personal_identity_facts(claims: Mapping[str, object]) -> PersonalIdentityFacts:
    issuer = (
        AbsentIssuer(kind="absent") if "iss" not in claims
        else DeclaredIssuer(value=claims["iss"]) if isinstance(claims["iss"], str)
        else MalformedIssuer(kind="malformed")
    )
    return PersonalIdentityFacts(
        issuer=issuer,
        subject=observed_identity_string(claims.get("sub")),
        tenant_id=observed_identity_string(claims.get("tid")),
        object_id=observed_identity_string(claims.get("oid")),
        delegated_scope=isinstance(observed_identity_string(claims.get("scp")), ObservedIdentityString),
        machine=machine_identity(claims),
    )


def personal_group_membership(value: object) -> GroupMembership:
    if isinstance(value, str):
        groups = (value,) if value.strip() else ()
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        groups = tuple(item for item in value if item.strip())
    else:
        groups = ()
    return GroupMembership(group_ids=tuple(sorted(set(groups))))


def simulated_user_claims(identity: SimulatedUserIdentity) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": identity.user_id, "email": identity.email, "name": identity.name,
    }
    if identity.simulated_admin:
        claims[identity.membership_claim] = [identity.required_membership]
    return claims


def authenticated_personal_mcp_claims(
    settings: AppConfig, policy: PersonalIdentityPolicy, claims: Mapping[str, object],
) -> Mapping[str, object]:
    if machine_identity(claims):
        return claims
    if not (local_personal_identity_enabled(policy) and settings.mcp.auth_mode == "single_test_user"):
        return claims
    authentication = settings.admin_authentication
    return simulated_user_claims(SimulatedUserIdentity(
        user_id=authentication.simulated_user_id,
        email=authentication.simulated_user_email,
        name=authentication.simulated_user_name,
        membership_claim=authentication.membership_claim,
        required_membership=authentication.required_membership,
        simulated_admin=authentication.simulated_admin,
    ))
