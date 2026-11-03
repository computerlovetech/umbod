from typing import TypeVar

from pydantic import BaseModel, ValidationError

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.identity_models import (
    AbsentIssuer, DeclaredIssuer, MalformedIssuer, ObservedIdentityString,
    UnavailableIdentityString, PersonalIdentityFacts, PersonalIdentityPolicy,
    PersonalIdentityRejection, ResolvedPersonalIdentity, UnresolvedPersonalIdentity,
)
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.personal_connections.identity_ports import PersonalIdentityResolver

resolver: PersonalIdentityResolver = canonical_principal
IdentityModel = TypeVar("IdentityModel", bound=BaseModel)


def replace(model: IdentityModel, **updates: object) -> IdentityModel:
    return type(model).model_validate({**model.model_dump(), **updates})


def policy() -> PersonalIdentityPolicy:
    return PersonalIdentityPolicy(
        enabled=True,
        identity_namespace="namespace",
        authentication_mode="oidc",
        authentication_environment="production",
        runtime_profile="production",
        runtime_auth="oidc",
        provider="google",
        expected_issuer="issuer",
        expected_tenant="tenant",
        simulated_subject="user",
    )


def facts() -> PersonalIdentityFacts:
    return PersonalIdentityFacts(
        issuer=DeclaredIssuer(value="issuer"),
        subject=ObservedIdentityString(value=" user "),
        tenant_id=UnavailableIdentityString(kind="unavailable"),
        object_id=UnavailableIdentityString(kind="unavailable"),
        delegated_scope=False,
        machine=False,
    )


def simulation_policy() -> PersonalIdentityPolicy:
    return replace(policy(), identity_namespace="test:local", authentication_mode="simulation", authentication_environment="development", runtime_profile="local", runtime_auth="dev")


def simulated_facts() -> PersonalIdentityFacts:
    return replace(facts(), issuer=AbsentIssuer(kind="absent"), subject=ObservedIdentityString(value="user"))


def test_typed_resolution_preserves_owner_strings() -> None:
    result = resolver(replace(policy(), identity_namespace=" namespace "), facts())
    assert isinstance(result, ResolvedPersonalIdentity)
    assert result.principal.subject == " user "
    assert result.principal.namespace == " namespace "


@pytest.mark.parametrize("issuer", [MalformedIssuer(kind="malformed"), DeclaredIssuer(value=""), DeclaredIssuer(value="other")])
def test_invalid_issuers_are_unresolved(issuer: MalformedIssuer | DeclaredIssuer) -> None:
    assert isinstance(resolver(policy(), replace(facts(), issuer=issuer)), UnresolvedPersonalIdentity)


def test_declared_issuer_requires_nonempty_configured_issuer() -> None:
    assert isinstance(resolver(replace(policy(), expected_issuer=""), replace(facts(), issuer=DeclaredIssuer(value=""))), UnresolvedPersonalIdentity)


def test_entra_resolves_without_raw_subject() -> None:
    result = resolver(replace(policy(), provider="azure_entra_id"), replace(facts(), subject=UnavailableIdentityString(kind="unavailable"), tenant_id=ObservedIdentityString(value="tenant"), object_id=ObservedIdentityString(value=" object "), delegated_scope=True))
    assert isinstance(result, ResolvedPersonalIdentity)
    assert result.principal.subject == "tenant: object "


def test_machine_is_rejected_even_with_entra_owner() -> None:
    result = resolver(replace(policy(), provider="azure_entra_id"), replace(facts(), machine=True, tenant_id=ObservedIdentityString(value="tenant"), object_id=ObservedIdentityString(value="object"), delegated_scope=True))
    assert result == UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.MACHINE)


def test_only_google_allows_absent_issuer() -> None:
    assert isinstance(resolver(policy(), replace(facts(), issuer=AbsentIssuer(kind="absent"))), ResolvedPersonalIdentity)
    assert isinstance(resolver(replace(policy(), provider="auth0"), replace(facts(), issuer=AbsentIssuer(kind="absent"))), UnresolvedPersonalIdentity)


@pytest.mark.parametrize("updates", [
    {"runtime_profile": "production"}, {"runtime_auth": "google"},
    {"authentication_mode": "disabled"}, {"authentication_environment": "production"},
    {"enabled": False}, {"identity_namespace": "test:"},
    {"identity_namespace": "test: "}, {"identity_namespace": " test:local"},
    {"identity_namespace": "test:local "}, {"identity_namespace": "namespace"},
    {"simulated_subject": " "},
])
def test_typed_local_simulation_requires_every_gate(updates: dict[str, object]) -> None:
    assert isinstance(resolver(replace(simulation_policy(), **updates), simulated_facts()), UnresolvedPersonalIdentity)


def test_typed_local_simulation_preserves_configured_subject() -> None:
    result = resolver(replace(simulation_policy(), simulated_subject=" user "), replace(simulated_facts(), subject=ObservedIdentityString(value=" user ")))
    assert isinstance(result, ResolvedPersonalIdentity)
    assert result.principal.subject == " user "


@pytest.mark.parametrize("issuer", [DeclaredIssuer(value=""), DeclaredIssuer(value="issuer"), MalformedIssuer(kind="malformed")])
def test_typed_local_simulation_requires_absent_issuer(issuer: DeclaredIssuer | MalformedIssuer) -> None:
    assert isinstance(resolver(simulation_policy(), replace(simulated_facts(), issuer=issuer)), UnresolvedPersonalIdentity)


@pytest.mark.parametrize("updates", [
    {"machine": "true"},
    {"machine": 1},
    {"delegated_scope": []},
    {"subject": {"value": 7}},
    {"issuer": {}},
    {"issuer": {"kind": "malformed", "value": "issuer"}},
    {"unexpected": True},
])
def test_public_resolver_argument_bundle_rejects_invalid_facts(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        resolver(policy(), PersonalIdentityFacts.model_validate({**facts().model_dump(), **updates}))


def test_public_resolver_requires_complete_facts() -> None:
    with pytest.raises(ValidationError):
        resolver(policy(), PersonalIdentityFacts.model_validate({}))


@pytest.mark.parametrize("issuer", [
    AbsentIssuer(kind="absent"),
    MalformedIssuer(kind="malformed"),
    DeclaredIssuer(value="issuer"),
])
def test_fact_json_roundtrip_preserves_issuer_state(issuer: AbsentIssuer | MalformedIssuer | DeclaredIssuer) -> None:
    original = replace(facts(), issuer=issuer)
    restored = PersonalIdentityFacts.model_validate_json(original.model_dump_json())
    assert restored == original
    assert type(restored.issuer) is type(issuer)
    assert resolver(policy(), restored) == resolver(policy(), original)


def test_malformed_issuer_roundtrip_never_gets_google_absence_exception() -> None:
    original = replace(facts(), issuer=MalformedIssuer(kind="malformed"))
    restored = PersonalIdentityFacts.model_validate_json(original.model_dump_json())
    assert resolver(policy(), restored) == UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.ISSUER)


def test_absent_google_issuer_still_allows_empty_expected_issuer() -> None:
    result = resolver(replace(policy(), expected_issuer=""), replace(facts(), issuer=AbsentIssuer(kind="absent")))
    assert isinstance(result, ResolvedPersonalIdentity)


def test_facts_are_immutable_including_nested_observations() -> None:
    original = facts()
    with pytest.raises(ValidationError, match="frozen_instance"):
        original.machine = True
    with pytest.raises(ValidationError, match="frozen_instance"):
        original.issuer.value = "other"


def test_policy_and_public_resolution_models_are_validated_and_immutable() -> None:
    configured = policy()
    result = resolver(configured, facts())
    assert isinstance(result, ResolvedPersonalIdentity)
    assert ResolvedPersonalIdentity.model_validate_json(result.model_dump_json()) == result
    rejected = resolver(configured, replace(facts(), machine=True))
    assert isinstance(rejected, UnresolvedPersonalIdentity)
    assert UnresolvedPersonalIdentity.model_validate_json(rejected.model_dump_json()) == rejected
    with pytest.raises(ValidationError, match="frozen_instance"):
        rejected.reason = PersonalIdentityRejection.SUBJECT
    with pytest.raises(ValidationError, match="frozen_instance"):
        configured.enabled = False
    with pytest.raises(ValidationError, match="frozen_instance"):
        result.principal = result.principal
    with pytest.raises(ValidationError):
        PersonalIdentityPolicy.model_validate({**configured.model_dump(), "enabled": "false"})
    with pytest.raises(ValidationError):
        UnresolvedPersonalIdentity.model_validate({"reason": "unknown"})
    with pytest.raises(ValidationError):
        ResolvedPersonalIdentity.model_validate({"principal": {}})


@pytest.mark.parametrize("model_type", [AbsentIssuer, MalformedIssuer, UnavailableIdentityString, DeclaredIssuer, ObservedIdentityString, ResolvedPersonalIdentity, UnresolvedPersonalIdentity])
def test_state_and_result_models_require_explicit_fields(model_type: type[BaseModel]) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate({})
