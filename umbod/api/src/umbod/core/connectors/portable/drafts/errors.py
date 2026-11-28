class DraftAuthorRequired(PermissionError):
    pass


class DraftRevisionNotFound(LookupError):
    pass


class DraftHeadChanged(RuntimeError):
    pass


class InvalidDraftSource(ValueError):
    pass


class DraftReadUnavailable(RuntimeError):
    pass


class DraftWriteUnconfirmed(RuntimeError):
    pass
