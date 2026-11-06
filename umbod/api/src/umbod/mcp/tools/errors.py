from logging import WARNING

from fastmcp.exceptions import ToolError, ValidationError

from umbod.core.responses import RetryAdvice, ToolErrorDetails, ToolNotice


class ToolAuthorizationDenied(ToolError):
    def __init__(self, message: str) -> None:
        super().__init__(message, log_level=WARNING)


class BuiltinToolError(ToolError):
    def __init__(self, message: str, *, details: ToolErrorDetails, retry: RetryAdvice) -> None:
        super().__init__(message)
        self.details = details
        self.retry = retry


class BuiltinToolRejected(BuiltinToolError):
    pass


class BuiltinToolArgumentError(ValidationError):
    def __init__(self, message: str, *, details: ToolErrorDetails, notices: tuple[ToolNotice, ...]) -> None:
        super().__init__(message)
        self.details = details
        self.notices = notices
        self.retry = RetryAdvice.AFTER_CORRECTION


class BuiltinToolAuthorizationDenied(ToolAuthorizationDenied):
    retry: RetryAdvice = RetryAdvice.AFTER_PERMISSION_CHANGE

    def __init__(self, message: str, *, details: ToolErrorDetails) -> None:
        super().__init__(message)
        self.details = details


class BuiltinToolApprovalDenied(BuiltinToolAuthorizationDenied):
    retry: RetryAdvice = RetryAdvice.NEVER


class ToolResponseContractError(ToolError):
    def __init__(self) -> None:
        super().__init__(
            "The tool response did not match its output schema. "
            "The operation may already have completed; check its state before retrying."
        )
