class UploadSessionError(Exception):
    pass


class UploadExpired(UploadSessionError):
    pass


class UploadConflict(UploadSessionError):
    pass


class UploadLengthMismatch(UploadSessionError):
    pass


class UploadMediaTypeMismatch(UploadSessionError):
    pass
