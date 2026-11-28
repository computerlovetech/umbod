from umbod_sdk.connectors import Connector


connector = Connector(
    id="configuration_probe",
    name="Configuration probe",
    description="Verifies inactive portable connector configuration.",
    capability_description="Provides a probe operation that must remain inactive.",
    configuration={
        "type": "object",
        "properties": {
            "workspace": {"type": "string", "title": "Workspace", "minLength": 1},
            "mode": {"type": "string", "title": "Mode", "enum": ["preview", "review"]},
        },
        "required": ["workspace", "mode"],
        "additionalProperties": False,
    },
)


@connector.configuration_check
async def check(*, configuration: dict[str, str]) -> bool:
    raise RuntimeError("Configuration check must not run for the inactive fixture")


@connector.tool(
    name="probe",
    description="Detect accidental execution of the inactive connector.",
    input_schema={"type": "object", "additionalProperties": False},
)
async def probe(*, configuration: dict[str, str]) -> dict[str, str]:
    raise RuntimeError("Tool must not run for the inactive fixture")
