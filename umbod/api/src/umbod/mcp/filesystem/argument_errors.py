import json
from typing import Any, Literal

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.responses import ToolArgumentIssue, ToolErrorDetails
from umbod.mcp.responses.arguments import DeclaredArgumentFields, argument_diagnostics, argument_notices
from umbod.mcp.tools.errors import BuiltinToolArgumentError


class InvalidArgumentJson(Exception):
    pass


def argument_json(arguments: dict[str, Any], *, allow_nan: bool) -> str:
    try:
        return json.dumps(arguments, allow_nan=allow_nan)
    except (TypeError, ValueError):
        raise InvalidArgumentJson() from None


def _prefix(name: str) -> str:
    if name in {"filesystem_upload", "filesystem_begin_upload", "filesystem_complete_upload"}:
        return "filesystem_invalid_upload: Invalid upload arguments"
    if name in {"filesystem_share", "filesystem_search_sharing_recipients"}:
        return "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    if name == "filesystem_delete_file":
        return "filesystem_invalid_delete: Invalid file deletion arguments"
    if name == "filesystem_browse":
        return "filesystem_invalid_browse: Invalid filesystem browsing arguments"
    if name == "update_filesystem_node":
        return "filesystem_invalid_update: Invalid filesystem update arguments"
    return "filesystem_invalid_arguments: Invalid filesystem arguments"


def _correction(kind: str, path: tuple[str, ...], fields: DeclaredArgumentFields, name: str) -> str:
    if kind == "extra_forbidden":
        return "Remove undeclared fields."
    if kind == "missing":
        return "Provide this required field."
    if path == ("metadata", "attributes"):
        return "Use an object with string attribute values."
    if path == ("metadata",) and kind == "value_error" and name == "update_filesystem_node":
        return "Provide an attribute or content_type change."
    if not path and kind == "value_error" and name == "update_filesystem_node":
        return "Provide at least one change: name, parent_id, or metadata."
    if path and path[-1] == "upload_id":
        return "Use the upload_id UUID returned by filesystem_begin_upload."
    if "uuid" in fields.fields.get(path, set()):
        return "Use a valid UUID returned by filesystem_browse."
    guidance = {
        ("size_bytes",): "Use a nonnegative integer equal to the actual original byte count.",
        ("expected_sha256",): "Use the computed lowercase 64-character hexadecimal SHA256, or omit this field.",
        ("expected_revision",): "Use the positive integer revision from the current filesystem_browse result.",
        ("depth",): "Use an integer from 1 through 16.",
        ("max_entries",): "Use an integer from 1 through 1000.",
        ("target", "path"): "Use an absolute path without NUL or dot segments, at most 4096 characters and 64 segments.",
        ("query",): "Use nonblank text of at most 200 characters.",
        ("group_id",): "Use a nonblank registered group ID returned by filesystem_search_sharing_recipients.",
        ("recipient", "group_id"): "Use a nonblank registered group ID returned by filesystem_search_sharing_recipients.",
        ("recipient", "user_id"): "Use a nonblank user ID of at most 200 characters returned by filesystem_search_sharing_recipients.",
        ("operation",): "Use ls, tree, stat, or home.",
        ("content", "encoding"): "Use utf-8 or base64.",
        ("recipient", "type"): "Use group or user.",
        ("recipient_type",): "Use group or user.",
        ("target", "type"): "Use root, path, or node.",
        ("permissions",): "Use a nonempty list of allowed permissions: discover, read, write, delete, share.",
    }
    if path in guidance:
        return guidance[path]
    types = fields.fields.get(path, set()) - {"uuid"}
    if types:
        return "Use the schema-declared type: " + " or ".join(sorted(types)) + "."
    return "Use arguments matching the tool input schema."


def _argument_error(name: str, issues: tuple[ToolArgumentIssue, ...], *, truncated: bool) -> BuiltinToolArgumentError:
    prefix = _prefix(name)
    code, message = prefix.split(": ", 1)
    displayed = [issue.field + ": " + issue.correction for issue in issues]
    if truncated:
        displayed.append("Additional issues omitted; correct these fields and retry.")
    return BuiltinToolArgumentError(
        prefix + ". " + " ".join(displayed or ["Use arguments matching the tool input schema."]),
        details=ToolErrorDetails(code=code, message=message, issues=issues),
        notices=argument_notices(truncated),
    )


def argument_validation_error(tool: Tool, error: ModelValidationError) -> BuiltinToolArgumentError:
    diagnostics = argument_diagnostics(tool, error, _correction)
    return _argument_error(tool.name, diagnostics.issues, truncated=diagnostics.truncated)


def invalid_content_error(encoding: Literal["utf-8", "base64"]) -> BuiltinToolArgumentError:
    issue = (
        ToolArgumentIssue(
            field="content.text", reason="invalid_encoding",
            correction="Use valid UTF-8 text without unpaired surrogates.",
        )
        if encoding == "utf-8" else ToolArgumentIssue(
            field="content.data", reason="invalid_encoding",
            correction="Use canonical padded base64 for the original bytes.",
        )
    )
    return _argument_error("filesystem_upload", (issue,), truncated=False)


class FilesystemArgumentErrorsTool(Tool):
    _delegate: Tool = PrivateAttr()

    def __init__(self, delegate: Tool) -> None:
        super().__init__(**{name: getattr(delegate, name) for name in Tool.model_fields})
        self._delegate = delegate

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            return await self._delegate.run(arguments)
        except ModelValidationError as error:
            raise argument_validation_error(self._delegate, error) from None
        except ValidationError as error:
            if isinstance(error.__cause__, ModelValidationError):
                raise argument_validation_error(self._delegate, error.__cause__) from None
            raise
        except InvalidArgumentJson:
            raise _argument_error(self.name, (ToolArgumentIssue(
                field="arguments", reason="invalid_json",
                correction="Submit valid JSON matching the tool input schema.",
            ),), truncated=False) from None
