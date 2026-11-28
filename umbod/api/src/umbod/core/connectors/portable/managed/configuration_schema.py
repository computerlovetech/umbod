from re import fullmatch, sub
from typing import Annotated, Literal, NotRequired, TypedDict

from pydantic import ConfigDict, Field, TypeAdapter, with_config

from ..draft_validation.models import ValidatedManifestSnapshot
from ..validation import json_snapshot
from .catalog_models import ManagedConfigurationField
from .models import InactiveConnectorSnapshot

MAX_CONFIGURATION_FIELDS = 16
MAX_CONFIGURATION_VALUE_LENGTH = 1024
_MAX_CONFIGURATION_SCHEMA_BYTES = 16 * 1024
_MAX_PINNED_SCHEMA_BYTES = _MAX_CONFIGURATION_SCHEMA_BYTES + MAX_CONFIGURATION_FIELDS * len(
    f',"maxLength":{MAX_CONFIGURATION_VALUE_LENGTH}',
)
_MAX_LABEL_LENGTH = 120
_MAX_ENUM_CHOICES = 16

_RESERVED_FIELD_NAMES = frozenset({
    "acceptcharset", "action", "autocomplete", "checkvalidity", "configuration", "connectorid", "constructor",
    "csrf", "csrftoken", "draftid", "elements", "encoding", "enctype", "form", "length", "meta", "method",
    "name", "novalidate", "prototype", "redirect", "rel", "rellist", "reportvalidity", "requestsubmit", "reset",
    "returnto", "revisionid", "status", "submit", "target", "tostring", "valueof",
})
_CREDENTIAL_MARKERS = (
    "accesskey", "apikey", "authentication", "authorization", "bearer", "credential", "passphrase",
    "password", "passwd", "privatekey", "secret", "signingkey", "token",
)


@with_config(ConfigDict(extra="forbid", strict=True))
class _StringSchema(TypedDict):
    type: Literal["string"]
    title: NotRequired[Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LENGTH)]]
    minLength: NotRequired[Annotated[int, Field(ge=0, le=MAX_CONFIGURATION_VALUE_LENGTH)]]
    maxLength: NotRequired[Annotated[int, Field(ge=0, le=MAX_CONFIGURATION_VALUE_LENGTH)]]
    enum: NotRequired[Annotated[list[Annotated[str, Field(max_length=MAX_CONFIGURATION_VALUE_LENGTH)]], Field(min_length=1, max_length=_MAX_ENUM_CHOICES)]]


@with_config(ConfigDict(extra="forbid", strict=True))
class _ConfigurationSchema(TypedDict):
    type: Literal["object"]
    properties: Annotated[dict[str, _StringSchema], Field(max_length=MAX_CONFIGURATION_FIELDS)]
    required: NotRequired[Annotated[list[str], Field(max_length=MAX_CONFIGURATION_FIELDS)]]
    additionalProperties: Literal[False]


_SCHEMA = TypeAdapter(_ConfigurationSchema)


class UnsupportedManagedConfiguration(ValueError):
    pass


class UnsupportedManagedManifest(ValueError):
    pass


def inactive_connector_snapshot(manifest: ValidatedManifestSnapshot) -> InactiveConnectorSnapshot:
    if manifest.manifest_version != 1:
        raise UnsupportedManagedManifest()
    if not (
        _valid_display_text(manifest.connector_id, 100)
        and _valid_display_text(manifest.display_name, _MAX_LABEL_LENGTH)
        and _valid_display_text(manifest.description, 1024)
    ):
        raise UnsupportedManagedManifest()
    return InactiveConnectorSnapshot(
        declared_connector_id=manifest.connector_id,
        display_name=manifest.display_name,
        description=manifest.description,
        configuration_schema_json=_configuration_schema(manifest.configuration_schema_json),
    )


def pinned_configuration_fields(raw_json: str) -> tuple[ManagedConfigurationField, ...]:
    schema = _read_configuration_schema(raw_json, _MAX_PINNED_SCHEMA_BYTES)
    required = set(schema.get("required", []))
    return tuple(
        ManagedConfigurationField(
            name=name,
            label=field.get("title", name),
            required=name in required,
            min_length=field.get("minLength", 0),
            max_length=field.get("maxLength", MAX_CONFIGURATION_VALUE_LENGTH),
            choices=tuple(field.get("enum", [])),
        )
        for name, field in schema["properties"].items()
    )


def _configuration_schema(raw_json: str) -> str:
    return json_snapshot(_read_configuration_schema(raw_json, _MAX_CONFIGURATION_SCHEMA_BYTES))


def _read_configuration_schema(raw_json: str, maximum_length: int) -> _ConfigurationSchema:
    try:
        if len(raw_json) > maximum_length:
            raise UnsupportedManagedConfiguration()
        schema = _SCHEMA.validate_json(raw_json)
        properties = schema["properties"]
        required = schema.get("required", [])
        if not set(required).issubset(properties) or len(set(required)) != len(required):
            raise UnsupportedManagedConfiguration()
        for name, definition in properties.items():
            _check_field(name, definition)
        return schema
    except ValueError:
        raise UnsupportedManagedConfiguration() from None


def _check_field(name: str, definition: _StringSchema) -> None:
    compact_name = _compact(name)
    if (
        not fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", name)
        or compact_name in _RESERVED_FIELD_NAMES
        or _is_credential_name(compact_name)
    ):
        raise UnsupportedManagedConfiguration()
    label = definition.get("title", name)
    if not _valid_display_text(label, _MAX_LABEL_LENGTH) or _is_credential_name(_compact(label)):
        raise UnsupportedManagedConfiguration()
    minimum = definition.get("minLength", 0)
    maximum = definition.get("maxLength", MAX_CONFIGURATION_VALUE_LENGTH)
    choices = definition.get("enum", [])
    if minimum > maximum or len(set(choices)) != len(choices) or any(
        not minimum <= len(choice) <= maximum or not choice.isprintable() and choice != "" for choice in choices
    ):
        raise UnsupportedManagedConfiguration()
    definition["maxLength"] = maximum


def _valid_display_text(value: str, maximum: int) -> bool:
    return bool(value.strip()) and len(value) <= maximum and value.isprintable()


def _compact(value: str) -> str:
    return sub(r"[^a-z0-9]", "", value.casefold())


def _is_credential_name(compact: str) -> bool:
    return any(marker in compact for marker in _CREDENTIAL_MARKERS)
