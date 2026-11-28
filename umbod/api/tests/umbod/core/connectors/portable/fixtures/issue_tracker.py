from umbod_sdk.connectors import Connector
from umbod_sdk.connectors.http import HttpContext


connector = Connector(
    id="issue_tracker",
    name="Issue tracker",
    description="Manage issues in the configured project.",
    capability_description="This connector reads and creates project issues.",
    configuration={"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]},
    http_targets={"tracker": "Read and create project issues"},
)


@connector.configuration_check
async def check(*, configuration: dict[str, str], context: HttpContext) -> bool:
    result = await context.request_status("tracker", path=["projects", configuration["project"]], query=[])
    return result.get("status") == 200


@connector.tool(name="read", description="List issues.", input_schema={"type": "object"})
async def read(*, configuration: dict[str, str], context: HttpContext) -> dict[str, object]:
    return await context.request(
        "tracker",
        path=["projects", configuration["project"], "issues"],
        query=[["label", "open"], ["label", "support"]],
        response_schema={"type": "array", "items": {"type": "integer"}},
    )


@connector.tool(
    name="create", description="Open an issue.",
    input_schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)
async def create(*, configuration: dict[str, str], context: HttpContext, title: str) -> dict[str, object]:
    return await context.post_status(
        "tracker",
        path=["projects", configuration["project"], "issues"],
        query=[],
        json_body={"title": title},
        request_schema={"type": "object", "properties": {"title": {"type": "string", "minLength": 1}}},
    )
