from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict

from umbod_sdk.connector_checks.compatibility import ReleaseMetadataError


class RegistryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    token: str
    accept: str


class RegistryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: bytes


class RegistryTransport(Protocol):
    def get(self, request: RegistryRequest) -> RegistryResponse: ...


class _RegistryRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, request: Request, response: object, code: int, message: str,
        headers: object, new_url: str,
    ) -> Request:
        parsed = urlsplit(new_url)
        if parsed.scheme != "https" or parsed.hostname not in {"ghcr.io", "pkg-containers.githubusercontent.com"} or parsed.port not in {None, 443} or parsed.username:
            raise ReleaseMetadataError("Registry redirected to an unsupported location")
        return Request(new_url, headers={"Accept": request.get_header("Accept", "application/json")})


class HttpRegistryTransport:
    def get(self, request: RegistryRequest) -> RegistryResponse:
        headers = {"Accept": request.accept, "User-Agent": "umbod-sdk"}
        if request.token:
            headers["Authorization"] = f"Bearer {request.token}"
        try:
            opener = build_opener(_RegistryRedirectHandler())
            with opener.open(Request(request.url, headers=headers), timeout=15) as response:
                content = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as error:
            detail = "release or metadata not found" if error.code == 404 else "access denied" if error.code in {401, 403} else "request failed"
            raise ReleaseMetadataError(f"Registry {detail} (HTTP {error.code}); no compatibility verdict available") from error
        except (URLError, OSError, ValueError, HTTPException) as error:
            raise ReleaseMetadataError("Registry metadata could not be read; check network access and retry") from error
        if len(content) > 4 * 1024 * 1024:
            raise ReleaseMetadataError("Registry metadata exceeds the permitted response size")
        return RegistryResponse(content=content)
