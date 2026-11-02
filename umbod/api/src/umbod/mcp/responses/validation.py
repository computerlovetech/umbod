from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.responses import OperationState, ToolErrorDetails
from umbod.mcp.tools.errors import BuiltinToolArgumentError

from .arguments import argument_diagnostics, argument_notices, generic_correction
from .progress import operation_state


class BuiltinArgumentErrorsTool(Tool):
    _delegate: Tool = PrivateAttr()

    def __init__(self, delegate: Tool) -> None:
        super().__init__(**{name: getattr(delegate, name) for name in Tool.model_fields})
        self._delegate = delegate

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            return await self._delegate.run(arguments)
        except ModelValidationError as error:
            if operation_state() != OperationState.NOT_STARTED:
                raise
            raise self._error(error) from None
        except ValidationError as error:
            if operation_state() != OperationState.NOT_STARTED or not isinstance(error.__cause__, ModelValidationError):
                raise
            raise self._error(error.__cause__) from None

    def _error(self, error: ModelValidationError) -> BuiltinToolArgumentError:
        diagnostics = argument_diagnostics(self._delegate, error, generic_correction)
        details = ToolErrorDetails(code="invalid_arguments", message="Invalid tool arguments.", issues=diagnostics.issues)
        text = details.message + " " + " ".join(issue.field + ": " + issue.correction for issue in details.issues)
        if diagnostics.truncated:
            text += " Additional issues omitted; correct these fields and retry."
        return BuiltinToolArgumentError(text, details=details, notices=argument_notices(diagnostics.truncated))
