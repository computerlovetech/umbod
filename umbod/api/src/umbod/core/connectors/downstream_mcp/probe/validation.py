from typing import Literal

from umbod.core.connectors.downstream_mcp.models import DomainModel


class DownstreamConnectorValidationSucceeded(DomainModel):
    valid: Literal[True] = True


class DownstreamConnectorValidationFailed(DomainModel):
    valid: Literal[False] = False
    code: Literal[
        "oauth_disabled",
        "endpoint_not_found",
        "auth_rejected",
        "unreachable",
        "timeout",
        "invalid_mcp_protocol",
    ]


DownstreamConnectorValidationResult = (
    DownstreamConnectorValidationSucceeded | DownstreamConnectorValidationFailed
)


class DownstreamConnectorValidationError(ValueError):
    def __init__(self, failure: DownstreamConnectorValidationFailed) -> None:
        self.code = failure.code
        super().__init__(failure.code)
