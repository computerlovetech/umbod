from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from umbod.core.responses import OperationState


class OperationProgress:
    def __init__(self) -> None:
        self.state: OperationState = OperationState.NOT_STARTED

    def started(self) -> None:
        self.state = OperationState.UNKNOWN

    def completed(self) -> None:
        self.state = OperationState.COMPLETED


_current_progress: ContextVar[Optional[OperationProgress]] = ContextVar("builtin_operation_progress", default=None)


@contextmanager
def operation_progress_context() -> Iterator[OperationProgress]:
    progress = OperationProgress()
    token = _current_progress.set(progress)
    try:
        yield progress
    finally:
        _current_progress.reset(token)


def operation_state() -> OperationState:
    progress = _current_progress.get()
    return progress.state if progress is not None else OperationState.UNKNOWN


def operation_started() -> None:
    progress = _current_progress.get()
    if progress is not None:
        progress.started()


def operation_completed() -> None:
    progress = _current_progress.get()
    if progress is not None:
        progress.completed()
