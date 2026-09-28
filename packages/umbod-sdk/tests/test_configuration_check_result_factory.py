from typing import Annotated

import pytest
from pydantic import Field, ValidationError

from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


@pytest.mark.parametrize("value", [True, False])
def test_constructor_retains_boolean_valid_field(value: bool) -> None:
    result = ConfigurationCheckResult(valid=value)

    assert result.valid is value
    assert result.model_dump()["valid"] is value


def test_valid_factory_returns_valid_result() -> None:
    result = ConfigurationCheckResult.valid()

    assert isinstance(result, ConfigurationCheckResult)
    assert result.valid is True
    assert result.model_dump() == {"valid": True, "message": None, "field_messages": {}}


@pytest.mark.parametrize(
    "arguments,details",
    [
        (("Invalid credentials",), {}),
        ((), {"message": "Invalid credentials"}),
        ((), {"field_messages": {"token": "Invalid token"}}),
        (("Invalid credentials",), {"field_messages": {"token": "Invalid token"}}),
    ],
)
def test_invalid_factory_preserves_message_and_field_messages(
    arguments: tuple[str, ...], details: dict[str, object]
) -> None:
    result = ConfigurationCheckResult.invalid(*arguments, **details)

    assert isinstance(result, ConfigurationCheckResult)
    assert result.valid is False
    assert result.message == (arguments[0] if arguments else details.get("message"))
    assert result.field_messages == details.get("field_messages", {})
    assert result.model_dump()["valid"] is False


def test_valid_field_remains_required_in_schema_and_validation() -> None:
    schema = ConfigurationCheckResult.model_json_schema()

    assert "valid" in schema["required"]
    assert schema["properties"]["valid"] == {"title": "Valid", "type": "boolean"}
    assert set(ConfigurationCheckResult.model_fields) == {"valid", "message", "field_messages"}
    with pytest.raises(ValidationError):
        ConfigurationCheckResult.model_validate({})


def test_subclasses_preserve_required_boolean_field_and_factories() -> None:
    class CustomResult(ConfigurationCheckResult):
        pass

    class DerivedResult(CustomResult):
        pass

    for result_type in (CustomResult, DerivedResult):
        assert result_type.model_fields["valid"].is_required()
        assert "valid" in result_type.model_json_schema()["required"]
        with pytest.raises(ValidationError):
            result_type.model_validate({})
        for value in (True, False):
            result = result_type.model_validate_json(f'{{"valid": {str(value).lower()}}}')
            assert result.valid is value
            assert result.model_dump()["valid"] is value
        assert isinstance(result_type.valid(), result_type)
        assert result_type.valid().valid is True
        assert isinstance(result_type.invalid("Invalid credentials"), result_type)
        assert result_type.invalid("Invalid credentials").valid is False


def test_subclass_explicit_valid_default_is_preserved() -> None:
    with pytest.warns(UserWarning, match='Field name "valid"'):
        class CustomResult(ConfigurationCheckResult):
            valid: bool = False

    assert CustomResult.model_fields["valid"].is_required() is False
    assert CustomResult().valid is False
    assert CustomResult.valid().valid is True


def test_registered_configuration_check_calls_valid_factory() -> None:
    class Configuration(Model):
        pass

    connector = Connector(
        id="sample",
        name="Sample",
        description="Sample connector.",
        capability_description="Read sample records.",
        configuration=Configuration,
    )

    @connector.configuration_check
    def check_configuration(configuration: Configuration) -> ConfigurationCheckResult:
        return ConfigurationCheckResult.valid()

    @connector.tool(description="Read a record.")
    def read_record(record_id: Annotated[str, Field(description="Record identifier.")]) -> str:
        return record_id

    result = connector.registration()["configuration_check"](Configuration())

    assert isinstance(result, ConfigurationCheckResult)
    assert result.valid is True
