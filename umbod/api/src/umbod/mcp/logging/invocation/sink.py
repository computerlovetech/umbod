from __future__ import annotations

import sys
from typing import Protocol, TextIO

from umbod.logging import (
    StructuredLogRecord as OpenTelemetryStructuredLogRecord,
    emit_structured_record,
    format_structured_record,
)
from umbod.mcp.logging.invocation.event import McpToolInvocationLogEvent
from umbod.mcp.logging.invocation.formatting import (
    McpToolInvocationLogFormatter,
    McpToolInvocationLogRecord,
    StructuredLogRecord,
    StructuredMcpToolInvocationLogFormatter,
)


class McpToolInvocationLogReader(Protocol):
    def invocation_records(self) -> tuple[McpToolInvocationLogRecord, ...]: ...


class McpToolInvocationLogSink(Protocol):
    def record_invocation_completed(self, event: McpToolInvocationLogEvent) -> None: ...


class StdoutMcpToolInvocationLogSink:
    def __init__(self, formatter: McpToolInvocationLogFormatter, *stream: TextIO | None) -> None:
        self._formatter = formatter
        self._stream = _resolve_stdout_stream(stream)
        self._uses_shared_logging = len(stream) == 0

    def record_invocation_completed(self, event: McpToolInvocationLogEvent) -> None:
        record = self._formatter.format_invocation_completed(event)
        structured_record = OpenTelemetryStructuredLogRecord(
            body=record.body,
            severity_text=record.severity_text,
            attributes=record.attributes,
            trace_id=record.trace_id,
            span_id=record.span_id,
        )
        if self._uses_shared_logging:
            emit_structured_record(structured_record)
            return
        self._stream.write(
            f"{format_structured_record('umbod', structured_record)}\n"
        )
        self._stream.flush()


class InMemoryMcpToolInvocationLogSink:
    def __init__(self, formatter: McpToolInvocationLogFormatter) -> None:
        self._formatter = formatter
        self._records: list[StructuredLogRecord] = []

    def record_invocation_completed(self, event: McpToolInvocationLogEvent) -> None:
        record = self._formatter.format_invocation_completed(event)
        self._records.append(record)

    def invocation_records(self) -> tuple[StructuredLogRecord, ...]:
        return tuple(self._records)


def create_default_mcp_tool_invocation_log_sink() -> McpToolInvocationLogSink:
    return StdoutMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())


def _resolve_stdout_stream(stream_arguments: tuple[TextIO | None, ...]) -> TextIO:
    if len(stream_arguments) > 1:
        raise TypeError("StdoutMcpToolInvocationLogSink accepts at most one stream")
    if len(stream_arguments) == 0:
        return sys.stdout
    return stream_arguments[0] or sys.stdout
