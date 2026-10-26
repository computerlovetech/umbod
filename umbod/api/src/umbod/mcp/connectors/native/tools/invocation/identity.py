from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorToolInvocationIdentity:
    tool_name: str
    connector_id: str
    connector_name: str
    operation_name: str
