import re

from umbod.core.connectors.native.runtime import ConnectorPromptMapping

PROMPT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def prompt_name(mapping: ConnectorPromptMapping) -> str:
    connector_id = getattr(mapping, "connector_id")
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{connector_id}_{mapping.name}").strip("_")
    if not PROMPT_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid connector prompt name after mangling: {name}")
    return name
