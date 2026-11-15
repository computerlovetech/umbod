from urllib.parse import urlencode, urlsplit

from umbod.config.app import validate_collector_base_url
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRequired, PersonalToolResult


def validate_recovery_origin(origin: str) -> str:
    validated = validate_collector_base_url(origin)
    if not validated or urlsplit(validated).path not in ("", "/"):
        raise ValueError("Personal recovery requires an absolute public site origin")
    return validated


def _recovery_destination(origin: str, connector_id: str) -> str:
    return f"{origin}/connectors?{urlencode({'connector': f'downstream_mcp:{connector_id}'})}"


def personal_inventory_failure(origin: str, connector_id: str) -> PersonalToolResult:
    destination = _recovery_destination(origin, connector_id)
    message = f"The expected tool inventory is out of date. Open {destination} and load tools. Then rediscover the tools before retrying this request. Do not automatically replay this operation."
    return PersonalToolResult(result={"isError": True, "content": [{"type": "text", "text": message}]})


def personal_authorization_failure(origin: str, connector_id: str, error: PersonalAuthorizationRequired) -> PersonalToolResult:
    destination = _recovery_destination(origin, connector_id)
    if error.reason == "refresh_in_progress":
        message = f"Authorization recovery is in progress. Open {destination} to check its status. After recovery, rediscover the tools. Do not retry until recovery finishes or automatically replay this operation."
    else:
        explanation = {
            "expired": "Personal connection authorization has expired.",
            "rejected": "The connected service rejected your authorization.",
            "refresh_blocked": "Personal connection authorization needs recovery.",
        }[error.reason]
        retry_guidance = "A previous attempt may have reached the service. Inspect its outcome before retrying a write; do not repeat a write with an unknown outcome." if error.reason == "rejected" else "Then retry this request only when safe."
        message = f"{explanation} Open {destination} and use Renew access or Sign in again. After recovery, rediscover the tools. {retry_guidance} Do not automatically replay this operation."
    return PersonalToolResult(result={"isError": True, "content": [{"type": "text", "text": message}]})
