from umbod_sdk.connectors import Connector
from umbod_sdk.connectors.http import HttpContext

connector = Connector(
    id="issue_reader",
    name="Issue reader",
    description="Read project issues.",
    capability_description="Read project issues.",
    configuration={"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]},
    http_targets={"issue_tracker": "Read and create issues in a configured tracker."},
)


@connector.configuration_check
async def check_tracker(*, configuration: dict[str, str], context: HttpContext) -> bool:
    result = await context.request_status("issue_tracker", path=["projects", configuration["project"]], query=[])
    return result == {"status": 200, "body": {"kind": "no_content"}}


@connector.tool(name="read_issues", description="Read issue titles.", input_schema={"type": "object"})
async def read_issues(*, configuration: dict[str, str], context: HttpContext) -> dict[str, object]:
    return await context.request(
        "issue_tracker",
        path=["projects", configuration["project"], "issues"],
        query=[["label", "open"], ["label", "customer support"]],
        response_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "title": {"type": "string"}},
                "required": ["id", "title"],
            },
        },
    )


@connector.tool(
    name="create_issue",
    description="Create an issue.",
    input_schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)
async def create_issue(*, configuration: dict[str, str], context: HttpContext, title: str) -> dict[str, object]:
    return await context.post(
        "issue_tracker",
        path=["projects", configuration["project"], "issues"],
        query=[],
        json_body={"title": title},
        request_schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
        response_schema={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    )