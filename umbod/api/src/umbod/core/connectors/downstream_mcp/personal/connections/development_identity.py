from .identity_models import PersonalIdentityPolicy


def local_personal_identity_enabled(policy: PersonalIdentityPolicy) -> bool:
    namespace = policy.identity_namespace
    return (
        policy.runtime_profile == "local"
        and policy.runtime_auth == "dev"
        and policy.authentication_mode == "simulation"
        and policy.authentication_environment == "development"
        and policy.enabled
        and namespace == namespace.strip()
        and namespace.startswith("test:")
        and bool(namespace.removeprefix("test:").strip())
        and bool(policy.simulated_subject.strip())
    )
