from collections.abc import AsyncGenerator

from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect, Request


class UploadLimitExceeded(MultiPartException):
    pass


class BoundedMultipartParser(MultiPartParser):
    def __init__(self, request: Request, max_bytes: int) -> None:
        super().__init__(
            request.headers, bounded_request_stream(request, max_bytes + 65_536),
            max_files=1, max_fields=2, max_part_size=16_384,
        )
        self._max_bytes = max_bytes
        self._file_bytes = 0
        self._complete = False

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._file_bytes += end - start
            if self._file_bytes > self._max_bytes:
                raise UploadLimitExceeded("File exceeds upload limit")
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self._complete = True
        super().on_end()

    async def parse(self) -> FormData:
        try:
            result = await super().parse()
            if not self._complete:
                raise MultiPartException("Incomplete multipart request")
            return result
        except BaseException:
            for temporary in self._files_to_close_on_error:
                temporary.close()
            raise


async def bounded_request_stream(request: Request, max_bytes: int) -> AsyncGenerator[bytes, None]:
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise UploadLimitExceeded("Request exceeds upload limit")
        yield chunk


MULTIPART_ERRORS = (MultiPartException, MultipartParseError, ClientDisconnect)
