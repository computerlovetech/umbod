from dataclasses import dataclass

from umbod.core.capabilities.tools.refs import ConnectorToolRef


@dataclass(frozen=True)
class UnrestrictedConnectorTools:
    def allows(self, tool_ref: ConnectorToolRef) -> bool:
        return True


@dataclass(frozen=True)
class RestrictedConnectorTools:
    allowed_tool_refs: frozenset[ConnectorToolRef]

    def allows(self, tool_ref: ConnectorToolRef) -> bool:
        return tool_ref in self.allowed_tool_refs


ConnectorToolAuthorizationScope = UnrestrictedConnectorTools | RestrictedConnectorTools
