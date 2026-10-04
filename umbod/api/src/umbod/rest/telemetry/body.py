import re
import zlib
from collections.abc import AsyncIterator

from starlette.requests import Request

from .errors import TelemetryHttpError


async def read_export_body(request: Request, max_request_bytes: int) -> bytes:
    encoding = request.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"identity", "gzip"}:
        raise TelemetryHttpError(415, "Unsupported content encoding")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        _check_content_length(content_length, max_request_bytes)
    chunks = _read_bounded_chunks(request, max_request_bytes)
    if encoding == "gzip":
        return await _read_gzip_body(chunks, max_request_bytes)
    output = bytearray()
    async for chunk in chunks:
        output.extend(chunk)
    return bytes(output)


def _check_content_length(content_length: str, max_request_bytes: int) -> None:
    if re.fullmatch(r"[0-9]+", content_length) is None:
        raise TelemetryHttpError(400, "Invalid content length")
    declared_length = content_length.lstrip("0") or "0"
    limit_text = str(max_request_bytes)
    if len(declared_length) > len(limit_text) or (
        len(declared_length) == len(limit_text) and declared_length > limit_text
    ):
        raise TelemetryHttpError(413, "Telemetry request too large")


async def _read_bounded_chunks(
    request: Request, max_request_bytes: int
) -> AsyncIterator[bytes]:
    wire_size = 0
    async for chunk in request.stream():
        wire_size += len(chunk)
        if wire_size > max_request_bytes:
            raise TelemetryHttpError(413, "Telemetry request too large")
        yield chunk


async def _read_gzip_body(
    chunks: AsyncIterator[bytes], max_request_bytes: int
) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    output = bytearray()
    async for chunk in chunks:
        pending = chunk
        while pending:
            if decompressor.eof:
                raise TelemetryHttpError(400, "Invalid gzip body")
            try:
                expanded = decompressor.decompress(
                    pending, max_request_bytes - len(output) + 1
                )
            except zlib.error:
                raise TelemetryHttpError(400, "Invalid gzip body") from None
            if len(output) + len(expanded) > max_request_bytes:
                raise TelemetryHttpError(413, "Telemetry request too large")
            output.extend(expanded)
            if decompressor.unused_data:
                raise TelemetryHttpError(400, "Invalid gzip body")
            pending = decompressor.unconsumed_tail
    if not decompressor.eof:
        raise TelemetryHttpError(400, "Invalid gzip body")
    return bytes(output)
