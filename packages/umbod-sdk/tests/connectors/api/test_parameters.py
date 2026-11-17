from typing import Annotated

import pytest
from jsonschema import Draft202012Validator, ValidationError
from pydantic import Field, create_model

from umbod_sdk.connectors import Connector
from umbod_sdk.connectors.api.parameters import (
    prompt_parameters_schema,
    resource_parameters_schema,
    tool_parameter_descriptions,
    tool_parameters_schema,
)
from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.uploaded_file import UploadedFile


class ConnectorConfiguration(Model):
    endpoint: str


class TaskFilter(Model):
    project_id: str


class SearchTasksRequest(Model):
    filters: list[TaskFilter]


class TaskNode(Model):
    name: str
    children: list["TaskNode"]


def _connector() -> Connector:
    return Connector(
        id="project_board",
        name="Project Board",
        description="Project Board connector.",
        capability_description="Search Project Board tasks.",
        configuration=ConnectorConfiguration,
    )


def test_model_arguments_publish_resolvable_nested_references() -> None:
    connector = _connector()

    @connector.tool(description="Search tasks.")
    def search_tasks(request: SearchTasksRequest) -> str:
        return request.filters[0].project_id

    schema = tool_parameters_schema(connector.definition().tools[0])
    validator = Draft202012Validator(schema)
    validator.validate({"request": {"filters": [{"project_id": "PB-1"}]}})

    with pytest.raises(ValidationError, match="project_id"):
        validator.validate({"request": {"filters": [{}]}})


def test_container_arguments_share_resolvable_model_definitions() -> None:
    connector = _connector()

    @connector.tool(description="Compare task filters.")
    def compare_filters(
        current: Annotated[list[TaskFilter], Field(description="Current filters.")],
        proposed: Annotated[TaskFilter | None, Field(description="Proposed filter.")],
    ) -> bool:
        return proposed in current

    schema = tool_parameters_schema(connector.definition().tools[0])
    validator = Draft202012Validator(schema)
    validator.validate({"current": [{"project_id": "PB-1"}], "proposed": None})
    validator.validate({"current": [], "proposed": {"project_id": "PB-2"}})

    with pytest.raises(ValidationError, match="project_id"):
        validator.validate({"current": [{}], "proposed": None})


def test_recursive_model_arguments_publish_resolvable_references() -> None:
    connector = _connector()

    @connector.tool(description="Inspect a task tree.")
    def inspect_tree(root: TaskNode) -> str:
        return root.name

    schema = tool_parameters_schema(connector.definition().tools[0])
    validator = Draft202012Validator(schema)
    validator.validate({"root": {"name": "root", "children": [{"name": "child", "children": []}]}})

    with pytest.raises(ValidationError, match="name"):
        validator.validate({"root": {"name": "root", "children": [{"children": []}]}})


def test_different_models_with_the_same_name_keep_distinct_definitions() -> None:
    connector = _connector()
    source_model = create_model("Record", source_id=(str, ...))
    destination_model = create_model("Record", destination_id=(int, ...))

    @connector.tool(
        description="Compare source and destination records.",
        parameters={"source": "Source record.", "destination": "Destination record."},
    )
    def compare_records(source: source_model, destination: destination_model) -> bool:
        return source == destination

    schema = tool_parameters_schema(connector.definition().tools[0])
    validator = Draft202012Validator(schema)
    validator.validate({"source": {"source_id": "PB-1"}, "destination": {"destination_id": 2}})

    with pytest.raises(ValidationError, match="destination_id"):
        validator.validate({"source": {"source_id": "PB-1"}, "destination": {"source_id": "PB-2"}})


@pytest.mark.parametrize("explicit_ellipsis", [False, True])
def test_required_field_defaults_agree_in_schema_and_descriptions(explicit_ellipsis: bool) -> None:
    connector = _connector()
    field = Field(..., description="Search query.") if explicit_ellipsis else Field(description="Search query.")

    @connector.tool(description="Search tasks.")
    def search_tasks(query: str = field) -> str:
        return query

    tool = connector.definition().tools[0]
    schema = tool_parameters_schema(tool)
    descriptions = tool_parameter_descriptions(tool)

    assert descriptions[0].required is True
    validator = Draft202012Validator(schema)
    validator.validate({"query": "launch"})
    with pytest.raises(ValidationError, match="query"):
        validator.validate({})


def test_explicit_defaults_keep_existing_optional_metadata() -> None:
    connector = _connector()

    @connector.tool(description="Search tasks.")
    def search_tasks(
        limit: Annotated[int, Field(description="Result limit.")] = 10,
        query: str = Field(default="launch", description="Search query."),
        labels: list[str] = Field(default_factory=list, description="Task labels."),
    ) -> int:
        return limit

    tool = connector.definition().tools[0]
    schema = tool_parameters_schema(tool)

    assert all(not description.required for description in tool_parameter_descriptions(tool))
    Draft202012Validator(schema).validate({})


def test_hidden_configuration_is_excluded_from_argument_schema() -> None:
    connector = _connector()

    @connector.tool(description="Read the configured endpoint.")
    def read_endpoint(configuration: ConnectorConfiguration) -> str:
        return configuration.endpoint

    assert tool_parameters_schema(connector.definition().tools[0]) == {"type": "object", "properties": {}}


def test_uploaded_file_keeps_binary_schema() -> None:
    connector = _connector()

    @connector.tool(description="Read an uploaded file.")
    def read_file(file: Annotated[UploadedFile, Field(description="Uploaded file.")]) -> bytes:
        return file.read()

    schema = tool_parameters_schema(connector.definition().tools[0])

    assert schema["properties"]["file"] == {
        "type": "string",
        "format": "binary",
        "x-umbod-file-input": True,
        "description": "Uploaded file.",
    }
    assert schema["required"] == ["file"]


def test_prompt_arguments_publish_resolvable_model_references() -> None:
    connector = _connector()

    @connector.prompt(description="Explain matching tasks.")
    def explain_tasks(request: SearchTasksRequest) -> str:
        return request.filters[0].project_id

    schema = prompt_parameters_schema(connector.definition().prompts[0])

    Draft202012Validator(schema).validate({"request": {"filters": [{"project_id": "PB-1"}]}})


def test_resource_arguments_publish_resolvable_model_references() -> None:
    connector = _connector()

    @connector.resource("tasks://{request}", name="tasks", description="Find matching tasks.")
    def find_tasks(request: SearchTasksRequest) -> str:
        return request.filters[0].project_id

    schema = resource_parameters_schema(connector.definition().resources[0])

    Draft202012Validator(schema).validate({"request": {"filters": [{"project_id": "PB-1"}]}})
