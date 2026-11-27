import ast
import inspect
import re
from pathlib import Path

import pytest

from umbod_sdk.connectors import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


class ConnectorConfiguration(Model):
    pass


@pytest.fixture
def connector() -> Connector:
    connector = Connector(
        id="declarations",
        name="Declarations",
        description="Declaration validation.",
        capability_description="Read declared records.",
        configuration=ConnectorConfiguration,
    )

    @connector.configuration_check
    def check_configuration(configuration: ConnectorConfiguration) -> ConfigurationCheckResult:
        return ConfigurationCheckResult.valid()

    return connector


def read_record() -> str:
    return "record"


@pytest.mark.parametrize(
    "first_options,second_options,operation_name",
    [
        ({"name": "shared"}, {"name": "shared"}, "shared"),
        ({}, {}, "read_record"),
        ({"name": "read_record"}, {}, "read_record"),
    ],
    ids=["explicit", "default", "explicit-default-collision"],
)
def test_registration_rejects_duplicate_tool_operation_names(
    connector: Connector,
    first_options: dict[str, str],
    second_options: dict[str, str],
    operation_name: str,
) -> None:
    connector.tool(description="Read a record.", **first_options)(read_record)
    connector.tool(description="Read another record.", **second_options)(read_record)

    with pytest.raises(ValueError) as error:
        connector.registration()

    assert "duplicate tool operation name" in str(error.value)
    assert connector.id in str(error.value)
    assert operation_name in str(error.value)


def test_registration_preserves_distinct_tool_operation_names(connector: Connector) -> None:
    connector.tool(description="Read a record.")(read_record)
    connector.tool(name="read_other", description="Read another record.")(read_record)

    registration = connector.registration()

    assert [tool["operation_name"] for tool in registration["tool_descriptions"]] == [
        "read_record",
        "read_other",
    ]


@pytest.mark.parametrize("option", ["output_schema", "descripton"])
def test_prompt_rejects_unknown_options(connector: Connector, option: str) -> None:
    with pytest.raises(TypeError, match=rf"prompt\(\).*unexpected keyword argument '{option}'"):
        connector.prompt(description="Read a prompt.", **{option: {}})


@pytest.mark.parametrize("option", ["output_schema", "descripton"])
def test_resource_rejects_unknown_options(connector: Connector, option: str) -> None:
    with pytest.raises(TypeError, match=rf"resource\(\).*unexpected keyword argument '{option}'"):
        connector.resource("records://{record_id}", description="Read a resource.", **{option: {}})


def test_prompt_accepts_supported_options(connector: Connector) -> None:
    @connector.prompt(
        name="record_prompt",
        description="Prepare a record prompt.",
        parameters={"record_id": "Record identifier."},
    )
    def prepare_prompt(record_id: str) -> str:
        return record_id

    registration = connector.registration()

    assert len(registration["prompt_descriptions"]) == 1
    prompt = registration["prompt_descriptions"][0]
    assert prompt["name"] == "record_prompt"
    assert prompt["description"] == "Prepare a record prompt."
    assert [
        (parameter.name, parameter.description, parameter.required)
        for parameter in prompt["parameters"]
    ] == [("record_id", "Record identifier.", True)]


def test_resource_accepts_supported_options(connector: Connector) -> None:
    @connector.resource(
        "records://{record_id}",
        name="record_resource",
        description="Read a record resource.",
        parameters={"record_id": "Record identifier."},
    )
    def read_resource(record_id: str) -> str:
        return record_id

    registration = connector.registration()

    assert registration["resource_descriptions"] == [
        {
            "uri_template": "records://{record_id}",
            "name": "record_resource",
            "description": "Read a record resource.",
            "parameters": {"record_id": "Record identifier."},
        }
    ]


@pytest.mark.parametrize(
    "document",
    ["README.md", "src/umbod_sdk/skills/draft-agent-connector/references/trusted-plugin.md"],
)
def test_documented_connector_constructors_supply_required_arguments(document: str) -> None:
    package_root = Path(__file__).resolve().parents[3]
    markdown = (package_root / document).read_text()
    constructor_signature = inspect.signature(Connector)
    required_arguments = {
        name
        for name, parameter in constructor_signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    constructors = [
        node
        for block in re.findall(r"```python\s*\n(.*?)```", markdown, flags=re.DOTALL)
        for node in ast.walk(ast.parse(block))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Connector"
    ]

    assert constructors, f"No Connector constructors found in {document}"
    for constructor in constructors:
        supplied_arguments = {keyword.arg for keyword in constructor.keywords}
        assert required_arguments <= supplied_arguments, (
            f"{document} constructor is missing {required_arguments - supplied_arguments}"
        )
