from umbod_sdk.connectors import Connector

connector = Connector(
    id="greeting",
    name="Greeting",
    description="Format a greeting.",
    capability_description="Greet a user.",
    configuration={
        "type": "object",
        "properties": {"prefix": {"type": "string", "minLength": 1}},
        "required": ["prefix"],
        "additionalProperties": False,
    },
)


@connector.configuration_check
def check_greeting(configuration: dict[str, str]) -> bool:
    return bool(configuration["prefix"].strip())


@connector.tool(
    name="greet",
    description="Greet a user.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Person to greet."},
            "punctuation": {"type": "string", "default": ""},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    output_schema={"type": "string"},
)
def greet(name: str, *, configuration: dict[str, str], punctuation: str = "") -> str:
    return f"{configuration['prefix']}, {name}{punctuation}"


@connector.tool(name="count", description="Return one.", input_schema={})
def count() -> int:
    return 1
