from pydantic import ConfigDict, model_validator

from umbod.proxies import Model
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools


class SharedRuntimeConnection(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: DiscoverDownstreamTools

    @model_validator(mode="after")
    def validate_shared_connection(self) -> "SharedRuntimeConnection":
        if uses_personal_oauth(self.command.definition):
            raise ValueError("Shared runtime requires a shared definition")
        if self.command.definition.connector_id != self.command.credential.connector_id:
            raise ValueError("Shared runtime credential identity mismatch")
        return self
