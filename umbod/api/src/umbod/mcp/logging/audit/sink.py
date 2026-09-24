from __future__ import annotations

import sys
from typing import TextIO

from umbod.logging import (
    StructuredLogRecord,
    emit_structured_record,
    format_structured_record,
)
from umbod.mcp.logging.audit.event import (
    McpAuditEvent,
    McpAuditEventSink,
    McpAuditFormatter,
)
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter


class StdoutMcpAuditEventSink:
    def __init__(self, formatter: McpAuditFormatter, *stream: TextIO | None) -> None:
        self._formatter = formatter
        self._stream = _resolve_stdout_stream(stream)
        self._uses_shared_logging = len(stream) == 0

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        record = self._formatter.format_mcp_activity(event)
        structured_record = StructuredLogRecord(
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


def create_default_mcp_audit_event_sink() -> McpAuditEventSink:
    return StdoutMcpAuditEventSink(StructuredMcpAuditFormatter())


def _resolve_stdout_stream(stream_arguments: tuple[TextIO | None, ...]) -> TextIO:
    if len(stream_arguments) > 1:
        raise TypeError("StdoutMcpAuditEventSink accepts at most one stream")
    if len(stream_arguments) == 0:
        return sys.stdout
    return stream_arguments[0] or sys.stdout
