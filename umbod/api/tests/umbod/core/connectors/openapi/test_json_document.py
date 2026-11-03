from typing import Any

import pytest

from umbod.core.connectors.openapi.importing import (
    JsonDocumentDecodeError,
    JsonDocumentErrorCode,
    decode_json_object,
)


@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"{}", {}), (b' \n {"openapi":"3.1.0"}\t', {"openapi": "3.1.0"})],
)
def test_decoder_accepts_exactly_one_object(content: bytes, expected: dict[str, Any]) -> None:
    assert decode_json_object(content) == expected


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", JsonDocumentErrorCode.MALFORMED_JSON),
        (b"   ", JsonDocumentErrorCode.MALFORMED_JSON),
        (b"{", JsonDocumentErrorCode.MALFORMED_JSON),
        (b"{}{}", JsonDocumentErrorCode.TRAILING_CONTENT),
        (b"{} true", JsonDocumentErrorCode.TRAILING_CONTENT),
        (b"[]", JsonDocumentErrorCode.OBJECT_REQUIRED),
        (b'"value"', JsonDocumentErrorCode.OBJECT_REQUIRED),
        (b"1", JsonDocumentErrorCode.OBJECT_REQUIRED),
        (b"true", JsonDocumentErrorCode.OBJECT_REQUIRED),
        (b"null", JsonDocumentErrorCode.OBJECT_REQUIRED),
        (b"\xff", JsonDocumentErrorCode.INVALID_UTF8),
    ],
)
def test_decoder_rejects_non_document_input(content: bytes, code: JsonDocumentErrorCode) -> None:
    with pytest.raises(JsonDocumentDecodeError) as caught:
        decode_json_object(content)

    assert caught.value.code is code
