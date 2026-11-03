from fastapi import Request
from fastapi.responses import JSONResponse, Response
from google.rpc.status_pb2 import Status

from .errors import TelemetryHttpError


JSON_MEDIA_TYPE = "application/json"
PROTOBUF_MEDIA_TYPE = "application/x-protobuf"
_STATUS_CODES = {400: 3, 401: 16, 413: 8, 415: 3, 503: 14}


def export_media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def export_success_response(media_type: str) -> Response:
    if media_type == PROTOBUF_MEDIA_TYPE:
        return Response(content=b"", status_code=200, media_type=PROTOBUF_MEDIA_TYPE)
    return JSONResponse(content={}, status_code=200)


async def telemetry_error_response(request: Request, exception: Exception) -> Response:
    if not isinstance(exception, TelemetryHttpError):
        raise exception
    headers = {"WWW-Authenticate": "Bearer"} if exception.status_code == 401 else {}
    code = _STATUS_CODES[exception.status_code]
    if export_media_type(request) == PROTOBUF_MEDIA_TYPE:
        return Response(
            content=Status(code=code, message=exception.message).SerializeToString(),
            status_code=exception.status_code,
            media_type=PROTOBUF_MEDIA_TYPE,
            headers=headers,
        )
    return JSONResponse(
        content={"code": code, "message": exception.message},
        status_code=exception.status_code,
        headers=headers,
    )
