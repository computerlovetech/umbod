import json
from collections.abc import AsyncIterator

import httpx2
from mcp import types
from pydantic import TypeAdapter

from .redaction import contains_secret
from .operation import OperationState


JSON_RPC_MESSAGE = TypeAdapter(types.JSONRPCMessage)

def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Invalid protocol JSON")
        result[key] = value
    return result


def reject_json_constant(value: str) -> object:
    raise ValueError("Invalid protocol JSON")


class ProtocolInputValidator:
    def __init__(self, state: OperationState) -> None:
        self._state = state
        self._token = state.target.access_token.get_secret_value()

    def text(self, value: str) -> None:
        if contains_secret(value, self._token):
            self._state.fail()

    def envelope(self, data: str) -> None:
        try:
            value = json.loads(data, object_pairs_hook=unique_json_object, parse_constant=reject_json_constant)
            if contains_secret(value, self._token):
                self._state.fail()
            JSON_RPC_MESSAGE.validate_python(value, strict=True, extra="forbid", by_alias=True, by_name=False)
            return
        except Exception:
            pass
        self._state.fail()

    def frame(self, lines: list[str]) -> bytes:
        data: list[str] = []
        for line in lines:
            self.text(line)
            name, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if name == "data":
                data.append(value)
        message = "\n".join(data)
        if message:
            self.envelope(message)
        return ("\n".join(lines) + "\n\n").encode("utf-8")


class EventFrameBuffer:
    def __init__(self, validator: ProtocolInputValidator, state: OperationState) -> None:
        self._validator = validator
        self._state = state
        self._pending = bytearray()
        self._lines: list[str] = []
        self._first_line = True

    def append(self, chunk: bytes) -> None:
        self._pending.extend(chunk)

    def frames(self, complete: bool) -> AsyncIterator[bytes]:
        return self._frames(complete)

    async def _frames(self, complete: bool) -> AsyncIterator[bytes]:
        while self._pending:
            end = next((index for index, byte in enumerate(self._pending) if byte in (10, 13)), -1)
            if end < 0 or (self._pending[end] == 13 and end + 1 == len(self._pending) and not complete):
                break
            width = 2 if self._pending[end:end + 2] == b"\r\n" else 1
            raw_line = bytes(self._pending[:end])
            del self._pending[:end + width]
            line = self._decode(raw_line)
            if self._first_line:
                line = line.removeprefix("\ufeff")
                self._first_line = False
            if line:
                self._validator.text(line)
                self._lines.append(line)
            else:
                frame = self._validator.frame(self._lines)
                self._lines = []
                yield frame
        if complete and (self._pending or self._lines):
            self._state.fail()

    def _decode(self, value: bytes) -> str:
        try:
            return value.decode("utf-8", errors="strict")
        except UnicodeError:
            pass
        self._state.fail()


class ValidatedProtocolStream(httpx2.AsyncByteStream):
    def __init__(self, raw: httpx2.AsyncByteStream, state: OperationState, media_type: str, allow_empty: bool) -> None:
        self._raw = raw
        self._state = state
        self._media_type = media_type
        self._allow_empty = allow_empty
        self._validator = ProtocolInputValidator(state)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._media_type == "text/event-stream":
            async for frame in self._events():
                yield frame
        else:
            body = bytearray()
            async for chunk in self._raw:
                body.extend(chunk)
            if not body and self._allow_empty:
                return
            if self._media_type != "application/json":
                self._state.fail()
            self._validate_json(bytes(body))
            yield bytes(body)

    async def _events(self) -> AsyncIterator[bytes]:
        buffer = EventFrameBuffer(self._validator, self._state)
        async for chunk in self._raw:
            buffer.append(chunk)
            async for frame in buffer.frames(complete=False):
                yield frame
        async for frame in buffer.frames(complete=True):
            yield frame

    def _validate_json(self, body: bytes) -> None:
        try:
            text = body.decode("utf-8", errors="strict")
        except UnicodeError:
            self._state.fail()
        self._validator.envelope(text)

    async def aclose(self) -> None:
        await self._raw.aclose()
