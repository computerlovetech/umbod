from typing import Protocol

from .models import ValidationOutcome


class DraftValidationUnavailable(RuntimeError):
    pass


class DraftSourceValidator(Protocol):
    @property
    def profile_id(self) -> str: ...

    async def validate(self, source: str) -> ValidationOutcome: ...
