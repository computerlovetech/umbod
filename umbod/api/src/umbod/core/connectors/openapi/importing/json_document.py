import json
from enum import Enum
from typing import Any


class JsonDocumentErrorCode(str, Enum):
    INVALID_UTF8 = "invalid_utf8"
    MALFORMED_JSON = "malformed_json"
    TRAILING_CONTENT = "trailing_content"
    OBJECT_REQUIRED = "object_required"


class JsonDocumentDecodeError(ValueError):
    def __init__(self, code: JsonDocumentErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def decode_json_object(content: bytes) -> dict[str, Any]:
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise JsonDocumentDecodeError(JsonDocumentErrorCode.INVALID_UTF8) from error
    stripped_text = text.lstrip()
    try:
        value, end = json.JSONDecoder().raw_decode(stripped_text)
    except json.JSONDecodeError as error:
        raise JsonDocumentDecodeError(JsonDocumentErrorCode.MALFORMED_JSON) from error
    if stripped_text[end:].strip():
        raise JsonDocumentDecodeError(JsonDocumentErrorCode.TRAILING_CONTENT)
    if not isinstance(value, dict):
        raise JsonDocumentDecodeError(JsonDocumentErrorCode.OBJECT_REQUIRED)
    return value
