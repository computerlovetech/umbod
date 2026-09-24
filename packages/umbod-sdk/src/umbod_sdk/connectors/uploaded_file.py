from dataclasses import dataclass, field as dataclass_field


@dataclass(frozen=True, init=False)
class UploadedFile:
    filename: str
    media_type: str
    size: int
    _data: bytes = dataclass_field(repr=False)

    def __init__(
        self,
        filename: str,
        media_type: str,
        size: int,
        data: bytes,
        *,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _UPLOADED_FILE_CONSTRUCTION_TOKEN:
            raise TypeError("UploadedFile instances are created by Umbod")
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "media_type", media_type)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "_data", data)

    def read(self) -> bytes:
        return self._data


_UPLOADED_FILE_CONSTRUCTION_TOKEN = object()


def create_uploaded_file(filename: str, media_type: str, data: bytes) -> UploadedFile:
    return UploadedFile(
        filename=filename,
        media_type=media_type,
        size=len(data),
        data=data,
        _construction_token=_UPLOADED_FILE_CONSTRUCTION_TOKEN,
    )
