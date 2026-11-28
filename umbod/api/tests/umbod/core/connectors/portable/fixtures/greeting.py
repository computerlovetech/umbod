from umbod_sdk.connectors import Connector


connector = Connector(
    id="greeting",
    name="Greeting",
    description="Compose a greeting.",
    capability_description="This connector greets people by name.",
    configuration={"type": "object", "properties": {"prefix": {"type": "string"}}, "required": ["prefix"]},
)


@connector.configuration_check
def check(*, configuration: dict[str, str]) -> bool:
    return bool(configuration["prefix"])


@connector.tool(
    name="greet", description="Greet by name.",
    input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    output_schema={"type": "string"},
)
def greet(*, configuration: dict[str, str], name: str) -> str:
    return configuration["prefix"] + ", " + name
