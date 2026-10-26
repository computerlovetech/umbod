from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, TypeAlias


class InvocationFailureOrigin(StrEnum):
    INTERNAL = "internal"
    CONNECTOR = "connector_execution"
    OPENAPI = "downstream_openapi"
    MCP = "downstream_mcp"


@dataclass(frozen=True)
class InvocationExceptionEvidence:
    origin: InvocationFailureOrigin
    exception_type: str
    stacktrace: str


@dataclass(frozen=True)
class InvocationReturnedFailure:
    origin: InvocationFailureOrigin


InvocationFailureEvidence: TypeAlias = InvocationExceptionEvidence | InvocationReturnedFailure

class _NoInvocationFailure:
    pass


@dataclass
class _InvocationFailureState:
    evidence: InvocationFailureEvidence | _NoInvocationFailure


_failure_state: ContextVar[Optional[_InvocationFailureState]] = ContextVar(
    "invocation_failure_state", default=None
)


def current_invocation_failure() -> Optional[InvocationFailureEvidence]:
    state = _failure_state.get()
    if state is None or isinstance(state.evidence, _NoInvocationFailure):
        return None
    return state.evidence


def _record_evidence(evidence: InvocationFailureEvidence) -> None:
    state = _failure_state.get()
    if state is None:
        _failure_state.set(_InvocationFailureState(evidence))
    else:
        state.evidence = evidence


@contextmanager
def invocation_failure_scope() -> Iterator[None]:
    token = _failure_state.set(_InvocationFailureState(_NoInvocationFailure()))
    try:
        yield
    finally:
        _failure_state.reset(token)


def capture_invocation_exception(
    error: BaseException, origin: InvocationFailureOrigin
) -> InvocationExceptionEvidence:
    evidence = exception_evidence(error, origin)
    _record_evidence(evidence)
    return evidence


def capture_returned_failure(origin: InvocationFailureOrigin) -> InvocationReturnedFailure:
    evidence = InvocationReturnedFailure(origin)
    _record_evidence(evidence)
    return evidence


def exception_evidence(
    error: BaseException, origin: InvocationFailureOrigin
) -> InvocationExceptionEvidence:
    lines: list[str] = []
    _append_exception(error, lines, set())
    return InvocationExceptionEvidence(
        origin=origin,
        exception_type=type(error).__qualname__,
        stacktrace="\n".join(lines),
    )


def _append_exception(error: BaseException, lines: list[str], seen: set[int]) -> None:
    if id(error) in seen:
        return
    if len(seen) >= 16:
        lines.append("[exception chain truncated]")
        return
    seen.add(id(error))
    cause = error.__cause__
    context = error.__context__
    if cause is not None:
        _append_exception(cause, lines, seen)
        lines.append("The above exception was the direct cause of the following exception:")
    elif context is not None:
        _append_exception(context, lines, seen)
        lines.append("During handling of the above exception, another exception occurred:")
    lines.append("Traceback (most recent call last):")
    traceback = error.__traceback__
    frame_count = 0
    while traceback is not None and frame_count < 40:
        code = traceback.tb_frame.f_code
        lines.append(f'  File "{code.co_filename}", line {traceback.tb_lineno}, in {code.co_name}')
        traceback = traceback.tb_next
        frame_count += 1
    if traceback is not None:
        lines.append("[traceback frames truncated]")
    lines.append(f"{type(error).__qualname__}: [message omitted]")
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions[:16]:
            _append_exception(nested, lines, seen)
        if len(error.exceptions) > 16:
            lines.append("[exception group truncated]")
