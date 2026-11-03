import pytest

from umbod.core.connectors.openapi.importing import (
    JsonPointerResolutionError,
    SameDocumentJsonPointerResolver,
)


def test_resolves_pointer_with_rfc6901_token_decoding() -> None:
    resolver = SameDocumentJsonPointerResolver({"a/b": {"~key": 7}}, maximum_depth=64)

    assert resolver.resolve("#/a~1b/~0key") == 7


@pytest.mark.parametrize("reference", ["#/missing", "#/bad~2token", "other.json#/value"])
def test_rejects_invalid_or_unsupported_pointer(reference: str) -> None:
    resolver = SameDocumentJsonPointerResolver({"value": 1}, maximum_depth=64)

    with pytest.raises(JsonPointerResolutionError):
        resolver.resolve(reference)


def test_rejects_reference_cycle() -> None:
    resolver = SameDocumentJsonPointerResolver(
        {"a": {"$ref": "#/b"}, "b": {"$ref": "#/a"}}, maximum_depth=64
    )

    with pytest.raises(JsonPointerResolutionError, match="cycle"):
        resolver.resolve("#/a")
