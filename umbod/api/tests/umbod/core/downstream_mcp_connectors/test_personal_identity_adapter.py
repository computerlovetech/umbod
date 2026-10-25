import pytest

from umbod.core.connectors.downstream_mcp.adapters.identity import personal_group_membership, personal_identity_facts
from umbod.core.connectors.downstream_mcp.personal_connections.identity_models import AbsentIssuer, DeclaredIssuer, MalformedIssuer


@pytest.mark.parametrize("claims", [
    {"idtyp": "app"}, {"gty": "client-credentials"}, {"gty": "client_credentials"},
    {"grant_type": "client_credentials"}, {"sub": "original@clients"},
    {"email": "robot.gserviceaccount.com"},
])
def test_original_machine_observations_survive_owner_claims(claims: dict[str, object]) -> None:
    facts = personal_identity_facts({**claims, "tid": "tenant", "oid": "object", "scp": "read"})
    assert facts.machine


@pytest.mark.parametrize("value", [[], {}, ["client_credentials"], {"grant": "client_credentials"}])
def test_malformed_grant_observations_remain_nonmachine(value: object) -> None:
    assert not personal_identity_facts({"sub": "owner", "gty": value}).machine


@pytest.mark.parametrize("value", [None, 7, [], {}, True])
def test_present_malformed_issuer_never_becomes_absent(value: object) -> None:
    assert isinstance(personal_identity_facts({"iss": value}).issuer, MalformedIssuer)


def test_empty_string_issuer_is_declared_not_absent() -> None:
    assert isinstance(personal_identity_facts({"iss": ""}).issuer, DeclaredIssuer)
    assert isinstance(personal_identity_facts({}).issuer, AbsentIssuer)


@pytest.mark.parametrize("value,expected", [
    (" team ", (" team ",)),
    (["b", "", " ", "a", "b", " a "], (" a ", "a", "b")),
    (("b", "a"), ("a", "b")),
    (["a", 1], ()),
    ({"a": True}, ()),
    (None, ()),
])
def test_personal_membership_normalization_is_strict_and_preserves_strings(value: object, expected: tuple[str, ...]) -> None:
    assert personal_group_membership(value).group_ids == expected
