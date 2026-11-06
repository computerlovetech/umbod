from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PersonalOAuthScopeMismatchObserved:
    """Sanitized fact published when a provider's scopes prevent personal sign-in.

    Carries only the connector identity, the failed OAuth step, and validated scope tokens.
    Tokens, codes, client secrets, and raw provider responses are never part of this event.
    """

    connector_id: str
    step: Literal["registration"]
    configured_scopes: tuple[str, ...]
    returned_scopes: tuple[str, ...]
