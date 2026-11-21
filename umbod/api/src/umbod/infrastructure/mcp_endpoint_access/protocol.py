import json
import re
from collections.abc import AsyncIterable, AsyncIterator

from mcp.types import InitializeResult

_REQUEST_ID = "umbod-initialize"
_PROTOCOL_VERSION = "2025-11-25"
_SUPPORTED_VERSIONS = {"2025-03-26", "2025-06-18", _PROTOCOL_VERSION}
INITIALIZE_REQUEST = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": _REQUEST_ID,
        "method": "initialize",
        "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "umbod-endpoint-check", "version": "1"},
        },
    },
    separators=(",", ":"),
).encode("ascii")


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    members: dict[str, object] = {}
    for name, value in pairs:
        if name in members:
            raise ValueError("Duplicate JSON member")
        members[name] = value
    return members


def _reject_constant(value: str) -> object:
    raise ValueError("Invalid JSON constant")


def _message(payload: bytes) -> dict[str, object]:
    message = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_members,
        parse_constant=_reject_constant,
    )
    if not isinstance(message, dict):
        raise ValueError("Expected a JSON-RPC object")
    return message


def _validate_result(message: dict[str, object]) -> bool:
    if (
        message.get("jsonrpc") != "2.0"
        or message.get("id") != _REQUEST_ID
        or "error" in message
        or "method" in message
    ):
        return False
    result = InitializeResult.model_validate(
        message.get("result"), strict=True, by_alias=True, by_name=False
    )
    return result.protocol_version in _SUPPORTED_VERSIONS


async def _sse_lines(chunks: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
    pending = bytearray()
    previous_ended_with_cr = False
    first_line = True
    async for chunk in chunks:
        if not chunk:
            continue
        if previous_ended_with_cr:
            chunk = chunk.removeprefix(b"\n")
        if not chunk:
            previous_ended_with_cr = False
            continue
        previous_ended_with_cr = chunk.endswith(b"\r")
        *lines, remainder = re.split(rb"\r\n|\r|\n", chunk)
        for line in lines:
            pending.extend(line)
            complete = bytes(pending)
            if first_line:
                complete = complete.removeprefix(b"\xef\xbb\xbf")
                first_line = False
            yield complete
            pending.clear()
        pending.extend(remainder)


async def _sse_messages(chunks: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
    event = b""
    data: list[bytes] = []
    async for line in _sse_lines(chunks):
        if not line:
            if event in {b"", b"message"} and any(data):
                yield b"\n".join(data)
            event = b""
            data.clear()
            continue
        field, _, value = line.partition(b":")
        value = value.removeprefix(b" ")
        if field == b"data":
            data.append(value)
        elif field == b"event":
            event = value


async def validate_initialization(
    media_type: bytes, chunks: AsyncIterable[bytes]
) -> bool:
    if media_type == b"application/json":
        body = bytearray()
        async for chunk in chunks:
            body.extend(chunk)
        return _validate_result(_message(bytes(body)))
    if media_type == b"text/event-stream":
        async for event in _sse_messages(chunks):
            message = _message(event)
            if message.get("id") == _REQUEST_ID and "method" not in message:
                return _validate_result(message)
    return False
