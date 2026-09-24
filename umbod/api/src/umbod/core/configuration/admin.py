from typing import Any, get_args, get_origin

from pydantic import SecretStr
from umbod.proxies import Model

from umbod.core.configuration.ports import ConnectorCurrentConfigurationStore
from umbod.core.configuration.models import ConnectorConfigurationField

MASKED_SECRET_VALUE = "**********"


def configuration_fields_from_schema(schema: type[Model]) -> list[ConnectorConfigurationField]:
    return [
        ConnectorConfigurationField(
            name=name,
            type=_configuration_field_type(field_info.annotation),
            required=field_info.is_required(),
            secret=_is_secret_annotation(field_info.annotation),
        )
        for name, field_info in schema.model_fields.items()
    ]


def masked_configuration_dump(configuration: Model) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for name, value in configuration.model_dump().items():
        if _is_secret_annotation(configuration.__class__.model_fields[name].annotation):
            masked[name] = MASKED_SECRET_VALUE
        elif isinstance(value, SecretStr):
            masked[name] = MASKED_SECRET_VALUE
        else:
            masked[name] = value
    return masked


async def validate_connector_configuration_input(**request: Any) -> Model:
    connector_id, schema, store, configuration = _connector_configuration_request(
        request, "validate_connector_configuration_input"
    )
    existing_configuration = await store.get_current_configuration(connector_id)
    if existing_configuration is None:
        return schema.model_validate(configuration)
    merged_configuration = _merge_with_existing_secret_values(
        schema=schema,
        existing_configuration=existing_configuration,
        configuration=configuration,
    )
    return schema.model_validate(merged_configuration)


async def save_connector_configuration(**request: Any) -> Model:
    connector_id, schema, store, configuration = _connector_configuration_request(
        request, "save_connector_configuration"
    )
    validated_configuration = await validate_connector_configuration_input(
        connector_id=connector_id,
        schema=schema,
        store=store,
        configuration=configuration,
    )
    await store.save_current_configuration(connector_id, validated_configuration)
    return validated_configuration


def _connector_configuration_request(
    request: dict[str, Any],
    function_name: str,
) -> tuple[str, type[Model], ConnectorCurrentConfigurationStore, dict[str, Any]]:
    expected_keys = {"connector_id", "schema", "store", "configuration"}
    unexpected_keys = set(request) - expected_keys
    if unexpected_keys:
        unexpected_key = sorted(unexpected_keys)[0]
        raise TypeError(f"{function_name}() got an unexpected keyword argument '{unexpected_key}'")
    missing_keys = expected_keys - set(request)
    if missing_keys:
        missing_key = sorted(missing_keys)[0]
        raise TypeError(
            f"{function_name}() missing 1 required keyword-only argument: '{missing_key}'"
        )
    return request["connector_id"], request["schema"], request["store"], request["configuration"]


def _merge_with_existing_secret_values(
    *,
    schema: type[Model],
    existing_configuration: Model,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    merged_configuration = dict(configuration)
    for name, field_info in schema.model_fields.items():
        if name not in merged_configuration and _is_secret_annotation(field_info.annotation):
            existing_value = getattr(existing_configuration, name)
            if isinstance(existing_value, SecretStr):
                merged_configuration[name] = existing_value.get_secret_value()
            else:
                merged_configuration[name] = existing_value
    return merged_configuration


def _configuration_field_type(annotation: Any) -> str:
    if _is_secret_annotation(annotation) or _contains_annotation(annotation, str):
        return "string"
    return "string"


def _is_secret_annotation(annotation: Any) -> bool:
    return _contains_annotation(annotation, SecretStr)


def _contains_annotation(annotation: Any, expected: type[Any]) -> bool:
    if annotation is expected:
        return True
    origin = get_origin(annotation)
    return (
        any(_contains_annotation(argument, expected) for argument in get_args(annotation))
        if origin
        else False
    )
