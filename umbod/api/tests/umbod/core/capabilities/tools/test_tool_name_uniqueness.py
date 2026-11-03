import pytest

from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, validate_unique_public_tool_names


def test_mangled_public_tool_name_collision_is_rejected() -> None:
    identities = (
        PublicToolIdentity(
            connector_id="alpha-id",
            tool_name_prefix="alpha",
            operation_name="weather/current",
        ),
        PublicToolIdentity(
            connector_id="beta-id",
            tool_name_prefix="alpha",
            operation_name="weather current",
        ),
    )

    with pytest.raises(PublicToolNameConflictError) as captured:
        validate_unique_public_tool_names(identities)

    assert captured.value.public_name == "alpha_weather_current"


def test_repeated_identical_public_tool_identity_is_rejected() -> None:
    identity = PublicToolIdentity(
        connector_id="alpha-id",
        tool_name_prefix="alpha",
        operation_name="forecast",
    )

    with pytest.raises(PublicToolNameConflictError) as captured:
        validate_unique_public_tool_names((identity, identity))

    assert captured.value.public_name == "alpha_forecast"
