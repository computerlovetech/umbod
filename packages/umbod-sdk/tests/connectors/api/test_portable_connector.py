import json
from collections.abc import Iterator
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from jsonschema.exceptions import SchemaError
from pydantic_monty import Monty, MontySession, MountDir

from umbod_sdk.connectors import Connector
from umbod_sdk.connectors.api.manifest import validate_manifest_schemas


CONNECTOR_FILE = Path(__file__).with_name("fixtures") / "portable_greeting.py"


@pytest.fixture
def connector() -> Connector:
    return run_path(str(CONNECTOR_FILE))["connector"]


@pytest.fixture
def monty_session(sdk_mount: MountDir) -> Iterator[MontySession]:
    with Monty() as pool:
        with pool.checkout(limits={"max_feed_duration_secs": 5, "max_memory": 32_000_000}) as session:
            session.feed_run("import umbod_sdk.connectors", mount=sdk_mount, cwd="/sdk")
            session.feed_run(CONNECTOR_FILE.read_text())
            yield session


def test_same_connector_source_exports_identical_manifest_in_cpython_and_monty(
    connector: Connector, monty_session: MontySession
) -> None:
    sandbox_manifest = validate_manifest_schemas(monty_session.feed_run("connector.manifest()"))

    assert sandbox_manifest == connector.manifest()


def test_same_connector_source_invokes_exported_tool_in_cpython_and_monty(
    connector: Connector, monty_session: MontySession
) -> None:
    manifest = connector.manifest()
    invocation = {"handler_id": manifest["tools"][0]["handler_id"], "arguments": {"name": "Ada"}}
    configuration = {"prefix": "Hello"}

    sandbox_result = monty_session.feed_run(
        'connector._handler(invocation["handler_id"])(configuration=configuration, **invocation["arguments"])',
        inputs={"invocation": invocation, "configuration": configuration},
    )
    host_result = connector._handler(invocation["handler_id"])(configuration=configuration, **invocation["arguments"])

    assert sandbox_result == host_result == "Hello, Ada"


def test_connector_metadata_is_readable_in_cpython_and_monty(
    connector: Connector, monty_session: MontySession
) -> None:
    sandbox_metadata = monty_session.feed_run(
        "[connector.id, connector.name, connector.description, connector.capability_description, connector.configuration]"
    )

    assert sandbox_metadata == [
        connector.id,
        connector.name,
        connector.description,
        connector.capability_description,
        connector.configuration,
    ]


def test_manifest_is_versioned_json_with_stable_and_distinct_handler_ids(connector: Connector) -> None:
    manifest = connector.manifest()
    assert json.loads(json.dumps(manifest, allow_nan=False)) == manifest == connector.manifest()
    assert manifest["manifest_version"] == 1
    assert manifest["connector_id"] == "greeting"
    first, second = manifest["tools"]
    assert [first["operation_name"], second["operation_name"]] == ["greet", "count"]
    assert first["output_schema"] == {"type": "string"}
    assert second["input_schema"] == {}
    assert "output_schema" not in second
    assert len({manifest["configuration_check_handler_id"], first["handler_id"], second["handler_id"]}) == 3


def test_manifest_returns_a_snapshot_of_its_schemas(connector: Connector) -> None:
    manifest = connector.manifest()
    manifest["tools"][0]["input_schema"]["required"].clear()

    assert connector.manifest()["tools"][0]["input_schema"]["required"] == ["name"]


def test_manifest_configuration_rejects_non_json_schema_values() -> None:
    connector = _connector(configuration={"default": float("nan")})
    connector.configuration_check(_check_configuration)
    connector.tool(name="read", description="Read a value.", input_schema={})(_read_value)

    with pytest.raises(ValueError, match="configuration_schema.default contains a non-JSON value"):
        connector.manifest()


@pytest.mark.parametrize(
    "schema,error,message",
    [
        ({"type": "unknown"}, SchemaError, "input_schema"),
        ({"$schema": "https://invalid.example/schema"}, SchemaError, "unsupported JSON Schema dialect"),
        ({"properties": {"configuration": {}}}, ValueError, "reserved 'configuration' parameter"),
        ({"allOf": [{"required": ["configuration"]}]}, ValueError, "reserved 'configuration' parameter"),
        (
            {"$ref": "#/$defs/arguments", "$defs": {"arguments": {"properties": {"configuration": {}}}}},
            ValueError,
            "reserved 'configuration' parameter",
        ),
        ({"$ref": "https://invalid.example/arguments"}, ValueError, "requires a local JSON Pointer"),
        ({"default": ("value",)}, ValueError, "non-JSON value"),
    ],
)
def test_manifest_rejects_invalid_explicit_input_schemas(
    schema: dict[str, Any], error: type[Exception], message: str
) -> None:
    connector = _connector(configuration={})
    connector.configuration_check(_check_configuration)
    connector.tool(name="read", description="Read a value.", input_schema=schema)(_read_value)

    with pytest.raises(error, match=message):
        connector.manifest()


def test_manifest_allows_configuration_fields_inside_nested_arguments() -> None:
    connector = _connector(configuration={})
    connector.configuration_check(_check_configuration)
    schema = {"properties": {"settings": {"properties": {"configuration": {"type": "string"}}}}}
    connector.tool(name="read", description="Read a value.", input_schema=schema)(_read_value)

    assert connector.manifest()["tools"][0]["input_schema"] == schema


def test_portable_tool_requires_an_explicit_input_schema() -> None:
    connector = _connector(configuration={})

    with pytest.raises(ValueError, match="requires input_schema"):
        connector.tool(name="read", description="Read a value.")(_read_value)


def test_portable_tool_requires_an_explicit_name() -> None:
    connector = _connector(configuration={})

    with pytest.raises(ValueError, match="require an explicit name"):
        connector.tool(description="Read a value.", input_schema={})(_read_value)


def test_portable_connector_rejects_duplicate_operation_names() -> None:
    connector = _connector(configuration={})
    connector.tool(name="read", description="Read a value.", input_schema={})(_read_value)

    with pytest.raises(ValueError, match="duplicate tool operation name: read"):
        connector.tool(name="read", description="Read another value.", input_schema={})(_read_value)


def test_portable_connector_requires_a_configuration_check() -> None:
    connector = _connector(configuration={})
    connector.tool(name="read", description="Read a value.", input_schema={})(_read_value)

    with pytest.raises(ValueError, match="requires a configuration check"):
        connector.manifest()


def test_portable_connector_directs_trusted_registration_callers_to_manifest(connector: Connector) -> None:
    with pytest.raises(ValueError, match=r"use manifest\(\)"):
        connector.registration()


def _connector(*, configuration: dict[str, Any]) -> Connector:
    return Connector(
        id="explicit",
        name="Explicit",
        description="Describe a portable connector.",
        capability_description="Read a value.",
        configuration=configuration,
    )


def _check_configuration(configuration: dict[str, Any]) -> bool:
    return True


def _read_value() -> str:
    return "value"
