from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER

from .development_identity import local_personal_identity_enabled
from .identity_models import (
    AbsentIssuer, DeclaredIssuer, ObservedIdentityString,
    PersonalIdentityFacts, PersonalIdentityPolicy, PersonalIdentityRejection,
    PersonalIdentityResolution, ResolvedPersonalIdentity, UnresolvedPersonalIdentity,
)
from .models import CanonicalPrincipal


def canonical_principal(
    policy: PersonalIdentityPolicy, facts: PersonalIdentityFacts,
) -> PersonalIdentityResolution:
    if not policy.enabled or not policy.identity_namespace.strip():
        return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.FEATURE_UNAVAILABLE)
    if policy.authentication_mode == "disabled":
        return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.AUTHENTICATION_DISABLED)
    if facts.machine:
        return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.MACHINE)
    if policy.authentication_mode == "simulation":
        if (
            not local_personal_identity_enabled(policy)
            or not (
                isinstance(facts.issuer, AbsentIssuer)
                or (isinstance(facts.issuer, DeclaredIssuer) and facts.issuer.value == LOCAL_DEVELOPMENT_ISSUER)
            )
            or not isinstance(facts.subject, ObservedIdentityString)
            or facts.subject.value != policy.simulated_subject
        ):
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.SIMULATION_UNAVAILABLE)
        return ResolvedPersonalIdentity(principal=CanonicalPrincipal(
            namespace=policy.identity_namespace, subject=facts.subject.value,
        ))
    if isinstance(facts.issuer, DeclaredIssuer):
        if not policy.expected_issuer or facts.issuer.value != policy.expected_issuer:
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.ISSUER)
    elif not (isinstance(facts.issuer, AbsentIssuer) and policy.provider == "google"):
        return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.ISSUER)
    if policy.provider == "azure_entra_id":
        if not isinstance(facts.tenant_id, ObservedIdentityString) or facts.tenant_id.value != policy.expected_tenant or not facts.tenant_id.value.strip():
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.TENANT)
        if not facts.delegated_scope:
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.DELEGATION)
        if not isinstance(facts.object_id, ObservedIdentityString) or not facts.object_id.value.strip():
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.SUBJECT)
        subject = f"{facts.tenant_id.value}:{facts.object_id.value}"
    else:
        if not isinstance(facts.subject, ObservedIdentityString) or not facts.subject.value.strip():
            return UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.SUBJECT)
        subject = facts.subject.value
    return ResolvedPersonalIdentity(principal=CanonicalPrincipal(
        namespace=policy.identity_namespace, subject=subject,
    ))
