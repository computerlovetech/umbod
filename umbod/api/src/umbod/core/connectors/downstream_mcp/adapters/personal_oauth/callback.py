from enum import Enum

from ...personal_connections.oauth_callback_models import validate_callback_uri
from .validation import validated_url


class CallbackURLPolicy(Enum):
    STRICT = "strict"
    LOCAL_DEVELOPMENT = "local_development"


def validate_callback_url(value: str, policy: CallbackURLPolicy) -> None:
    if not value.startswith("http://"):
        validated_url(value)
        return
    if policy is not CallbackURLPolicy.LOCAL_DEVELOPMENT:
        raise ValueError("Invalid callback URL")
    validate_callback_uri(value)
