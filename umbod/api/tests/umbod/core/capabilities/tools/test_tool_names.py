import pytest

from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, PublicToolNameValidator, mangle_public_tool_name


@pytest.mark.parametrize("prefix", ["billing", "Billing_API-2", "_internal"])
def test_public_tool_name_validator_accepts_valid_prefix(prefix: str) -> None:
    assert PublicToolNameValidator().validate_prefix(prefix) == prefix


@pytest.mark.parametrize("prefix", ["", "billing api", "billing.api", "billing/api"])
def test_public_tool_name_validator_rejects_invalid_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        PublicToolNameValidator().validate_prefix(prefix)


def test_public_tool_name_mangling_replaces_hyphens_with_underscores() -> None:
    assert mangle_public_tool_name("agent-backend", "get-domain") == "agent_backend_get_domain"


def test_public_tool_name_mangling_rejects_a_name_without_valid_characters() -> None:
    with pytest.raises(ValueError):
        mangle_public_tool_name("-", "-")


def test_public_tool_name_validator_rejects_public_name_collision() -> None:
    identities = (
        PublicToolIdentity(
            connector_id="first", tool_name_prefix="billing", operation_name="search"
        ),
        PublicToolIdentity(
            connector_id="second", tool_name_prefix="billing", operation_name="search"
        ),
    )

    with pytest.raises(PublicToolNameConflictError):
        PublicToolNameValidator().validate_unique(identities)
