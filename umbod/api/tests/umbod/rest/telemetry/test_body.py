import gzip

import pytest
from starlette.requests import Request
from starlette.types import Message

from umbod.rest.telemetry.body import read_export_body
from umbod.rest.telemetry.errors import TelemetryHttpError


def make_request(chunks: list[bytes], headers: dict[str, str]) -> Request:
    messages = iter(
        [
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
            for index, chunk in enumerate(chunks)
        ]
    )

    async def receive() -> Message:
        return next(messages)

    return Request(
        {
            "type": "http",
            "headers": [
                (key.encode(), value.encode()) for key, value in headers.items()
            ],
        },
        receive,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [{}, {"content-encoding": "identity"}, {"content-length": "00005"}]
)
async def test_identity_accepts_exact_limit(headers: dict[str, str]) -> None:
    assert await read_export_body(make_request([b"123", b"45"], headers), 5) == b"12345"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [{}, {"content-length": "6"}, {"content-length": "9" * 5000}]
)
async def test_identity_rejects_wire_over_limit(headers: dict[str, str]) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(make_request([b"123", b"456"], headers), 5)
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_declared_oversized_body_rejected_without_reading_stream() -> None:
    async def receive() -> Message:
        raise AssertionError("Must not consume oversized request")

    request = Request({"type": "http", "headers": [(b"content-length", b"6")]}, receive)
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(request, 5)
    assert error.value.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("length", ["-1", "bad", "1.5", "", "+1", "1,1"])
async def test_invalid_content_length_rejected(length: str) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(make_request([b""], {"content-length": length}), 100)
    assert error.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["br", "deflate", "gzip, identity"])
async def test_unsupported_encoding_rejected(encoding: str) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(make_request([b""], {"content-encoding": encoding}), 100)
    assert error.value.status_code == 415


@pytest.mark.asyncio
async def test_gzip_exact_expanded_limit_with_single_byte_chunks() -> None:
    source = b"a" * 256
    compressed = gzip.compress(source)
    chunks = [bytes([byte]) for byte in compressed]
    assert (
        await read_export_body(make_request(chunks, {"content-encoding": "gzip"}), 256)
        == source
    )


@pytest.mark.asyncio
async def test_gzip_exact_limit_accepts_empty_chunks_after_eof() -> None:
    source = b"a" * 256
    compressed = gzip.compress(source)
    request = make_request([b"", compressed, b"", b""], {"content-encoding": "gzip"})
    assert await read_export_body(request, 256) == source


@pytest.mark.asyncio
@pytest.mark.parametrize("trailer_index", [-8, -4])
async def test_gzip_rejects_crc_and_size_corruption_in_separate_chunks(
    trailer_index: int,
) -> None:
    compressed = bytearray(gzip.compress(b"a" * 256))
    compressed[trailer_index] ^= 1
    chunks = [bytes([byte]) for byte in compressed]
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(make_request(chunks, {"content-encoding": "gzip"}), 256)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_gzip_exact_wire_limit() -> None:
    compressed = gzip.compress(b"{}")
    assert (
        await read_export_body(
            make_request([compressed], {"content-encoding": "gzip"}), len(compressed)
        )
        == b"{}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source,limit", [(b"a" * 1_000_000, 1024), (b"{}", 10)])
async def test_gzip_rejects_expanded_or_wire_overflow(
    source: bytes, limit: int
) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(
            make_request([gzip.compress(source)], {"content-encoding": "gzip"}), limit
        )
    assert error.value.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"bad",
        gzip.compress(b"{}")[0:-1],
        gzip.compress(b"{}") + b"x",
        gzip.compress(b"{}") + gzip.compress(b"{}"),
        gzip.compress(b"{}")[:-8] + b"12345678",
    ],
)
async def test_invalid_gzip_is_rejected(body: bytes) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(make_request([body], {"content-encoding": "gzip"}), 1024)
    assert error.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", [b"x", gzip.compress(b"{}")])
async def test_gzip_trailing_later_chunk_is_rejected(suffix: bytes) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        await read_export_body(
            make_request([gzip.compress(b"{}"), suffix], {"content-encoding": "gzip"}),
            1024,
        )
    assert error.value.status_code == 400
