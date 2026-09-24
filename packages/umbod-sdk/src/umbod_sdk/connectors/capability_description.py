import unicodedata
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

CAPABILITY_DESCRIPTION_MAX_LENGTH = 300


def validate_capability_description(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("capability description must not be blank")
    if len(normalized) > CAPABILITY_DESCRIPTION_MAX_LENGTH:
        raise ValueError(
            f"capability description must not exceed {CAPABILITY_DESCRIPTION_MAX_LENGTH} characters"
        )
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError("capability description must be plain text without control characters")
    return normalized


CapabilityDescription = Annotated[
    str,
    StringConstraints(max_length=CAPABILITY_DESCRIPTION_MAX_LENGTH),
    AfterValidator(validate_capability_description),
]

__all__ = [
    "CAPABILITY_DESCRIPTION_MAX_LENGTH",
    "CapabilityDescription",
    "validate_capability_description",
]
