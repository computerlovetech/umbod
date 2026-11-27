import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from math import isfinite
from typing import Any, Protocol, TypedDict, Unpack
from unicodedata import category
from urllib.parse import urlencode

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from umbod_sdk.connectors.declaration import is_http_target_id

__all__ = [
    "HttpPolicyDenied",
    "HttpPostRequest",
    "HttpRequest",
    "HttpRequestBoundary",
    "HttpTransport",
    "RawHttpResponse",
]

_REQUEST_FIELDS = frozenset({"target", "method", "path", "query", "response_mode"})
_POST_FIELDS = frozenset({"json_body", "request_schema"})
_PATH_FORBIDDEN = frozenset("/\\%:?#")
_MAX_PATH_BYTES = 2 * 1024
_MAX_QUERY_PAIRS = 32
_MAX_QUERY_BYTES = 4 * 1024
_MAX_BODY_BYTES = 1024 * 1024
_MAX_SCHEMA_BYTES = 16 * 1024
_UNSUPPORTED_SCHEMA_KEYWORDS = frozenset({"pattern", "patternProperties"})
_DIALECT = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class HttpRequest:
    target: str
    method: str
    path: tuple[str, ...]
    query: tuple[tuple[str, str], ...]
    response_mode: str


@dataclass(frozen=True)
class HttpPostRequest(HttpRequest):
    body: bytes


@dataclass(frozen=True)
class RawHttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    async def send(self, request: HttpRequest) -> RawHttpResponse: ...


class HttpPolicyDenied(RuntimeError):
    pass


class _BoundaryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _BoundaryOptions(TypedDict, total=False):
    approved_post_paths: tuple[tuple[str, tuple[str, ...]], ...]


class HttpRequestBoundary:
    def __init__(
        self,
        *,
        targets: Mapping[str, str],
        transport: HttpTransport,
        **options: Unpack[_BoundaryOptions],
    ) -> None:
        if options.keys() - {"approved_post_paths"}:
            raise TypeError("Unexpected HTTP request boundary option")
        self._targets = frozenset(targets)
        self._transport = transport
        self._approved_post_paths = frozenset(options.get("approved_post_paths", ()))

    async def dispatch(self, request: object) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise _BoundaryError("invalid_request")
            outgoing = _prepare_request(request)
            if outgoing.target not in self._targets:
                raise _BoundaryError("unknown_target")
            if outgoing.method == "POST" and (outgoing.target, outgoing.path) not in self._approved_post_paths:
                raise _BoundaryError("policy_denied")
            decode_body = _body_decoder(outgoing, request)
            response = await self._send(_attach_request_body(outgoing, request))
            return _response_result(response, decode_body)
        except _BoundaryError as error:
            return {"error": error.code}

    async def _send(self, request: HttpRequest) -> RawHttpResponse:
        try:
            return await self._transport.send(request)
        except HttpPolicyDenied:
            raise _BoundaryError("policy_denied") from None
        except TimeoutError:
            raise _BoundaryError("outcome_unknown" if request.method == "POST" else "timeout") from None
        except Exception:
            raise _BoundaryError("outcome_unknown" if request.method == "POST" else "transport_error") from None


def _prepare_request(fields: Mapping[object, object]) -> HttpRequest:
    mode = fields.get("response_mode")
    target = fields.get("target")
    if not isinstance(mode, str) or mode not in ("json", "status"):
        raise _BoundaryError("invalid_request")
    expected = (
        _REQUEST_FIELDS | {"response_schema"} if mode == "json" else _REQUEST_FIELDS
    )
    method = fields.get("method")
    if type(method) is not str or method not in ("GET", "POST"):
        raise _BoundaryError("invalid_request")
    if method == "POST":
        expected = expected | _POST_FIELDS
    if set(fields) != expected:
        raise _BoundaryError("invalid_request")
    if not isinstance(target, str) or not is_http_target_id(target):
        raise _BoundaryError("invalid_request")
    return HttpRequest(
        target, method, _path(fields["path"]), _query(fields["query"]), mode
    )


def _attach_request_body(request: HttpRequest, fields: Mapping[object, object]) -> HttpRequest:
    if request.method == "GET":
        return request
    validator = _schema_validator(fields["request_schema"])
    try:
        payload = _copy_json(fields["json_body"])
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except RecursionError, TypeError, ValueError:
        raise _BoundaryError("invalid_request") from None
    if len(body) > _MAX_BODY_BYTES:
        raise _BoundaryError("limit_exceeded")
    try:
        validator.validate(payload)
    except ArithmeticError, RecursionError, Unresolvable, ValidationError, ValueError:
        raise _BoundaryError("request_contract_mismatch") from None
    return HttpPostRequest(request.target, request.method, request.path, request.query, request.response_mode, body)


def _path(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _BoundaryError("invalid_request")
    segments: list[str] = []
    size = max(0, len(value) - 1)
    for segment in value:
        if not isinstance(segment, str) or not segment or segment in (".", ".."):
            raise _BoundaryError("invalid_request")
        if size + len(segment) > _MAX_PATH_BYTES:
            raise _BoundaryError("limit_exceeded")
        if any(
            character in _PATH_FORBIDDEN
            or character.isspace()
            or category(character) in ("Cc", "Cf")
            for character in segment
        ):
            raise _BoundaryError("invalid_request")
        try:
            size += len(segment.encode("utf-8"))
        except UnicodeError:
            raise _BoundaryError("invalid_request") from None
        if size > _MAX_PATH_BYTES:
            raise _BoundaryError("limit_exceeded")
        segments.append(segment)
    return tuple(segments)


def _query(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise _BoundaryError("invalid_request")
    if len(value) > _MAX_QUERY_PAIRS:
        raise _BoundaryError("limit_exceeded")
    pairs: list[tuple[str, str]] = []
    size = max(0, len(value) - 1)
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise _BoundaryError("invalid_request")
        key, item = pair
        if not isinstance(key, str) or not key or not isinstance(item, str):
            raise _BoundaryError("invalid_request")
        if size + len(key) + len(item) + 1 > _MAX_QUERY_BYTES:
            raise _BoundaryError("limit_exceeded")
        try:
            size += len(urlencode([(key, item)]))
        except UnicodeError:
            raise _BoundaryError("invalid_request") from None
        if size > _MAX_QUERY_BYTES:
            raise _BoundaryError("limit_exceeded")
        pairs.append((key, item))
    return tuple(pairs)


def _body_decoder(
    request: HttpRequest, fields: Mapping[object, object]
) -> Callable[[RawHttpResponse], dict[str, Any]]:
    if request.response_mode == "status":
        return _no_content
    validator = _schema_validator(fields["response_schema"])
    return partial(_json_body, validator=validator)


def _schema_validator(value: object) -> Draft202012Validator:
    if not isinstance(value, dict) or not value:
        raise _BoundaryError("invalid_request")
    try:
        schema = _copy_json(value)
        schema_size = len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    except RecursionError, TypeError, ValueError:
        raise _BoundaryError("invalid_request") from None
    if schema_size > _MAX_SCHEMA_BYTES:
        raise _BoundaryError("limit_exceeded")
    try:
        Draft202012Validator.check_schema(schema)
        registry: Registry[Any] = Registry()
        _check_schema_resources(schema, registry)
        return Draft202012Validator(schema, registry=registry)
    except (
        ArithmeticError,
        RecursionError,
        SchemaError,
        Unresolvable,
        ValueError,
        TypeError,
    ):
        raise _BoundaryError("invalid_request") from None


def _check_schema_resources(schema: dict[str, Any], registry: Registry[Any]) -> None:
    root = DRAFT202012.create_resource(schema)
    pending = [(root, registry.resolver_with_root(root))]
    references = []
    schema_nodes: set[int] = set()
    while pending:
        resource, resolver = pending.pop()
        contents = resource.contents
        schema_nodes.add(id(contents))
        if isinstance(contents, bool):
            continue
        if _UNSUPPORTED_SCHEMA_KEYWORDS.intersection(contents):
            raise ValueError
        if contents.get("$schema", _DIALECT) not in (_DIALECT, _DIALECT + "#"):
            raise ValueError
        for key in ("$ref", "$dynamicRef"):
            if key in contents:
                references.append((contents[key], resolver))
        for child in DRAFT202012.subresources_of(contents):
            subresource = DRAFT202012.create_resource(child)
            pending.append((subresource, resolver.in_subresource(subresource)))
    for reference, resolver in references:
        if id(resolver.lookup(reference).contents) not in schema_nodes:
            raise ValueError


def _copy_json(value: object) -> Any:
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        value.encode("utf-8")
        return value
    if type(value) is float and isfinite(value):
        return value
    if type(value) is list:
        return [_copy_json(item) for item in value]
    if type(value) is dict:
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError
            key.encode("utf-8")
            copied[key] = _copy_json(item)
        return copied
    raise ValueError


def _response_result(
    response: RawHttpResponse, decode_body: Callable[[RawHttpResponse], dict[str, Any]]
) -> dict[str, Any]:
    if not isinstance(response, RawHttpResponse) or not isinstance(
        response.status, int
    ):
        raise _BoundaryError("invalid_response")
    status = int(response.status)
    if not 200 <= status <= 599:
        raise _BoundaryError("invalid_response")
    if 300 <= status <= 399:
        raise _BoundaryError("redirect_disallowed")
    body = (
        _no_content(response)
        if status in (204, 205) or status >= 400
        else decode_body(response)
    )
    return {"status": status, "body": body}


def _no_content(_response: RawHttpResponse) -> dict[str, Any]:
    return {"kind": "no_content"}


def _json_body(
    response: RawHttpResponse, *, validator: Draft202012Validator
) -> dict[str, Any]:
    body = response.body
    if not isinstance(body, bytes):
        raise _BoundaryError("invalid_response")
    if len(body) > _MAX_BODY_BYTES:
        raise _BoundaryError("limit_exceeded")
    try:
        decoded = _copy_json(json.loads(body.decode("utf-8")))
    except RecursionError, ValueError:
        raise _BoundaryError("invalid_response") from None
    try:
        validator.validate(decoded)
    except ArithmeticError, RecursionError, Unresolvable, ValidationError, ValueError:
        raise _BoundaryError("response_contract_mismatch") from None
    return {"kind": "json", "value": decoded}
