from typing import Protocol

from .models import CallerContext


class CallerContextProvider(Protocol):
    def get_context(self) -> CallerContext: ...
