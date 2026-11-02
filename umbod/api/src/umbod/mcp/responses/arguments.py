from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastmcp.tools.base import Tool
from pydantic import ValidationError as ModelValidationError

from umbod.core.responses import ToolArgumentIssue, ToolNotice


def argument_notices(truncated: bool) -> tuple[ToolNotice, ...]:
    if not truncated:
        return ()
    return (ToolNotice(
        code="argument_issues_truncated",
        message="Additional issues omitted; correct these fields and retry.",
    ),)


class DeclaredArgumentFields:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.fields: dict[tuple[str, ...], set[str]] = {}
        self.labels: dict[tuple[str, ...], set[str]] = {}
        self.discriminators: dict[tuple[str, ...], str] = {}
        self.arrays: set[tuple[str, ...]] = set()
        self.root_branches: set[str] = set()
        self._remaining = 4096
        self._visit(schema, (), schema, frozenset(), 0)

    def _visit(
        self, node: object, path: tuple[str, ...], root: dict[str, Any],
        references: frozenset[str], depth: int,
    ) -> None:
        self._remaining -= 1
        if not isinstance(node, dict) or depth > 32 or self._remaining < 0:
            return
        declared_type = node.get("type")
        types = self.fields.setdefault(path, set())
        if isinstance(declared_type, str) and declared_type in {
            "string", "integer", "number", "boolean", "object", "array", "null",
        }:
            types.add(declared_type)
        if node.get("format") == "uuid":
            types.add("uuid")
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/") and reference not in references:
            self.labels.setdefault(path, set()).add(reference[8:])
            definitions = root.get("$defs")
            if isinstance(definitions, dict):
                self._visit(definitions.get(reference[8:]), path, root, references | {reference}, depth + 1)
        if path == ("metadata", "attributes"):
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            for name, child in properties.items():
                if isinstance(name, str):
                    self._visit(child, (*path, name), root, references, depth + 1)
        discriminator = node.get("discriminator")
        if isinstance(discriminator, dict):
            name = discriminator.get("propertyName")
            if isinstance(name, str):
                self.discriminators[path] = name
        for keyword in ("oneOf", "anyOf"):
            branches = node.get(keyword)
            if not isinstance(branches, list):
                continue
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                labels = self.labels.setdefault(path, set())
                reference = branch.get("$ref")
                if isinstance(reference, str) and reference.startswith("#/$defs/"):
                    label = reference[8:]
                    labels.add(label)
                    if not path and not discriminator:
                        self.root_branches.add(label)
                mapping = discriminator.get("mapping") if isinstance(discriminator, dict) else None
                if isinstance(mapping, dict):
                    labels.update(label for label in mapping if isinstance(label, str))
                self._visit(branch, path, root, references, depth + 1)
        if isinstance(node.get("items"), dict):
            self.arrays.add(path)
            self._visit(node["items"], path, root, references, depth + 1)

    def canonical_path(self, location: tuple[Any, ...]) -> tuple[str, ...]:
        path: tuple[str, ...] = ()
        for part in location:
            if path == ("metadata", "attributes"):
                break
            if isinstance(part, str) and (*path, part) in self.fields:
                path = (*path, part)
            elif isinstance(part, str) and self._is_branch_label(part, path):
                continue
            elif isinstance(part, int) and path in self.arrays:
                continue
            else:
                break
        return path

    def _is_branch_label(self, part: str, path: tuple[str, ...]) -> bool:
        labels = self.labels.get(path, set())
        if part in labels:
            return True
        return part.startswith(("function-after[", "function-before[", "function-wrap[")) and any(
            part.endswith(", " + label + "]") for label in labels
        )


@dataclass(frozen=True)
class ArgumentDiagnostics:
    issues: tuple[ToolArgumentIssue, ...]
    truncated: bool


def generic_correction(kind: str, path: tuple[str, ...], fields: DeclaredArgumentFields, name: str) -> str:
    if kind == "extra_forbidden":
        return "Remove undeclared fields."
    if kind == "missing":
        return "Provide this required field."
    if kind in {"union_tag_invalid", "union_tag_not_found", "literal_error", "enum"}:
        return "Use a value allowed by the tool input schema."
    if kind in {"string_too_short", "string_too_long", "string_pattern_mismatch", "value_error"}:
        return "Use a value satisfying the field constraints in the tool input schema."
    types = fields.fields.get(path, set())
    if types:
        return "Use the schema-declared type: " + " or ".join(sorted(types)) + "."
    return "Use arguments matching the tool input schema."


def argument_diagnostics(
    tool: Tool, error: ModelValidationError,
    correction: Callable[[str, tuple[str, ...], DeclaredArgumentFields, str], str],
) -> ArgumentDiagnostics:
    fields = DeclaredArgumentFields(tool.parameters)
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    counts = Counter(
        issue["loc"][0] for issue in errors
        if issue["loc"] and issue["loc"][0] in fields.root_branches
    )
    selected = min(counts, key=lambda label: (counts[label], label)) if counts else None
    normalized: list[tuple[tuple[str, ...], str]] = []
    for issue in errors:
        location = issue["loc"]
        if location and location[0] in fields.root_branches and location[0] != selected:
            continue
        kind = issue["type"]
        path = fields.canonical_path(location[:-1] if kind == "extra_forbidden" else location)
        if kind in {"union_tag_invalid", "union_tag_not_found"}:
            discriminator = fields.discriminators.get(path)
            if discriminator is not None and (*path, discriminator) in fields.fields:
                path = (*path, discriminator)
        normalized.append((path, kind))
    issues: list[ToolArgumentIssue] = []
    reasons = {
        "missing": "required",
        "extra_forbidden": "undeclared_field",
        "union_tag_invalid": "invalid_option",
        "union_tag_not_found": "required_option",
        "literal_error": "invalid_option",
        "enum": "invalid_option",
        "greater_than": "outside_allowed_range",
        "greater_than_equal": "outside_allowed_range",
        "less_than": "outside_allowed_range",
        "less_than_equal": "outside_allowed_range",
        "string_too_short": "invalid_length",
        "string_too_long": "invalid_length",
        "string_pattern_mismatch": "invalid_format",
        "uuid_parsing": "invalid_uuid",
        "uuid_type": "invalid_uuid",
        "int_type": "invalid_type",
        "int_parsing": "invalid_type",
        "string_type": "invalid_type",
        "dict_type": "invalid_type",
        "list_type": "invalid_type",
        "bool_type": "invalid_type",
        "json_invalid": "invalid_json",
    }
    for path, kind in normalized:
        if kind in {"is_instance_of", "needs_python_object"} and any(
            len(other) > len(path) and other[:len(path)] == path for other, _ in normalized
        ):
            continue
        issue = ToolArgumentIssue(
            field=".".join(path) if path else "arguments",
            reason=reasons.get(kind, "invalid_value"),
            correction=correction(kind, path, fields, tool.name),
        )
        if issue not in issues:
            issues.append(issue)
    return ArgumentDiagnostics(issues=tuple(issues[:8]), truncated=len(issues) > 8)
