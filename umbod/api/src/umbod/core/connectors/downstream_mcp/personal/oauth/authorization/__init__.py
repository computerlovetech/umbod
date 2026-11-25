from importlib import import_module
from typing import TYPE_CHECKING, Any

from .models import (
    ClaimPersonalOAuthAttempt,
    ClaimedPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    ExchangePersonalOAuth,
    FailPersonalOAuthAttempt,
    FinishCallback,
    PersonalOAuthAttemptQuery,
    PersonalOAuthAttemptView,
    PersonalOAuthConflict,
    PersonalOAuthModel,
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PersonalOAuthUnavailable,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from .ports import PersonalOAuthAttemptStore, PersonalOAuthProvider

if TYPE_CHECKING:
    from .service import PersonalOAuthCallbackService, PersonalOAuthService

__all__ = [
    "ClaimPersonalOAuthAttempt",
    "ClaimedPersonalOAuthAttempt",
    "CompletePersonalOAuthAttempt",
    "ExchangePersonalOAuth",
    "FailPersonalOAuthAttempt",
    "FinishCallback",
    "PersonalOAuthAttemptQuery",
    "PersonalOAuthAttemptStore",
    "PersonalOAuthAttemptView",
    "PersonalOAuthCallbackService",
    "PersonalOAuthConflict",
    "PersonalOAuthModel",
    "PersonalOAuthProvider",
    "PersonalOAuthProviderFailure",
    "PersonalOAuthProviderUnsupported",
    "PersonalOAuthService",
    "PersonalOAuthUnavailable",
    "PreparePersonalOAuth",
    "PreparedPersonalOAuth",
    "PublishPersonalOAuthAttempt",
    "ReservePersonalOAuthAttempt",
]


def __getattr__(name: str) -> Any:
    if name not in {"PersonalOAuthCallbackService", "PersonalOAuthService"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(".service", __name__), name)
    globals()[name] = value
    return value
