from umbod.core.administrator.connector_configuration import ConfigurationRejected
from umbod.core.responses import RetryAdvice, ToolArgumentIssue, ToolErrorDetails
from umbod.mcp.tools.errors import BuiltinToolRejected


_REJECTION_DETAILS: dict[str, ToolErrorDetails] = {
    "connector_not_found": ToolErrorDetails(
        code="connector_not_found",
        message="The connector was not found.",
        issues=(ToolArgumentIssue(
            field="connector_id",
            reason="connector_not_found",
            correction="Select an existing connector and verify its kind.",
        ),),
    ),
    "capability_not_found": ToolErrorDetails(
        code="capability_not_found",
        message="A requested capability was not found on the connector.",
        issues=(ToolArgumentIssue(
            field="desired_state.operations",
            reason="capability_not_found",
            correction="Read the connector configuration and select an existing capability.",
        ),),
    ),
    "revision_conflict": ToolErrorDetails(
        code="revision_conflict",
        message="The connector configuration changed concurrently.",
        issues=(ToolArgumentIssue(
            field="desired_state.operations",
            reason="revision_conflict",
            correction="Read the current configuration before preparing updated revisions.",
        ),),
    ),
    "duplicate_target": ToolErrorDetails(
        code="duplicate_target",
        message="The desired state contains duplicate configuration targets.",
        issues=(ToolArgumentIssue(
            field="desired_state.operations",
            reason="duplicate_target",
            correction="Provide only one operation for each configuration target.",
        ),),
    ),
}
_GENERIC_REJECTION = ToolErrorDetails(
    code="configuration_rejected",
    message="The connector configuration request was rejected.",
    issues=(),
)


def configuration_rejection_error(result: ConfigurationRejected) -> BuiltinToolRejected:
    details = _REJECTION_DETAILS.get(result.error.code, _GENERIC_REJECTION)
    return BuiltinToolRejected(
        details.message,
        details=details,
        retry=RetryAdvice.AFTER_CORRECTION,
    )
