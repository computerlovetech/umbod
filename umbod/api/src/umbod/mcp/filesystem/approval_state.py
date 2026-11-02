from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.callers import CallerContext, CallerSnapshot

from .models import DeleteFileCommand


class FileDeletionApprovalDenied(Exception):
    pass


class FileDeletionApprovalState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    purpose: Literal["filesystem_delete_file:v1"]
    caller: CallerContext
    client_id: str
    command: DeleteFileCommand
    expires_at: int
    nonce: str = Field(min_length=1, pattern=r"^filesystem-delete:.+")


class FileDeletionApprovalStateCodec:
    def __init__(
        self, clock: Callable[[], float], random_token: Callable[[], str]
    ) -> None:
        self._clock = clock
        self._random_token = random_token

    def mint(
        self, caller: CallerSnapshot, command: DeleteFileCommand, client_id: str
    ) -> str:
        return FileDeletionApprovalState(
            purpose="filesystem_delete_file:v1",
            caller=caller.caller,
            client_id=client_id,
            command=command,
            expires_at=int(self._clock()) + 300,
            nonce=f"filesystem-delete:{self._random_token()}",
        ).model_dump_json()

    def verify(
        self,
        token: str,
        caller: CallerSnapshot,
        command: DeleteFileCommand,
        client_id: str,
    ) -> FileDeletionApprovalState:
        try:
            state = FileDeletionApprovalState.model_validate_json(token)
            if (
                state.caller != caller.caller
                or state.command != command
                or state.client_id != client_id
                or self._clock() >= state.expires_at
            ):
                raise FileDeletionApprovalDenied("File deletion approval state invalid")
            return state
        except Exception:
            raise FileDeletionApprovalDenied("File deletion approval state invalid") from None
