import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from io import StringIO
from keyword import iskeyword
from tokenize import TokenError, generate_tokens
from typing import Literal

from pydantic_monty import AsyncMontySession, MontyRuntimeError, MontySyntaxError

from umbod.core.connectors.portable.draft_validation.models import (
    DraftDiagnostic,
    SourcePosition,
)


_SOURCE_BYTE_LIMIT = 64 * 1024
_IMPORT_LIMIT = 20
_MODULE_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")


type _ImportNode = ast.Import | ast.ImportFrom | ast.Call


@dataclass(frozen=True, slots=True)
class _DetectedImport:
    module: str
    kind: Literal["absolute", "relative", "dynamic", "unsupported"]
    position: SourcePosition
    member: str


async def inspect_handler_imports(
    session: AsyncMontySession, source: str
) -> tuple[tuple[DraftDiagnostic, ...], bool]:
    if not _within_source_limit(source):
        return (
            _unverified(
                "Saved source is too large to inspect for handler imports.", ()
            ),
        ), True
    try:
        tree = ast.parse(source)
    except SyntaxError, UnicodeError, RecursionError:
        return (
            _unverified("Saved source could not be inspected for handler imports.", ()),
        ), False

    lines = _source_lines(source)
    probes: set[tuple[str, str]] = set()
    diagnostics: list[DraftDiagnostic] = []
    truncated = False
    for node in _import_nodes(tree, handler_only=True):
        for candidate in _detected_imports(node, lines):
            if candidate.kind == "absolute":
                key = (candidate.module, candidate.member)
                if key in probes:
                    continue
                if len(probes) == _IMPORT_LIMIT:
                    truncated = True
                    continue
                probes.add(key)
                result = await _probe_import(session, candidate)
                if result == "available":
                    continue
                diagnostic = _probe_diagnostic(candidate, result)
            else:
                diagnostic = _unverified(
                    _unverified_message(candidate), (candidate.position,)
                )
            if len(diagnostics) < _IMPORT_LIMIT:
                diagnostics.append(diagnostic)
            else:
                truncated = True
    return tuple(diagnostics), truncated


def module_on_import_line(source: str, line: int) -> str:
    if line < 1 or not _within_source_limit(source):
        return ""
    try:
        tree = ast.parse(source)
    except SyntaxError, UnicodeError, RecursionError:
        return ""
    lines = _source_lines(source)
    matches = (
        candidate
        for node in _import_nodes(tree, handler_only=False)
        if node.lineno <= line <= (node.end_lineno or node.lineno)
        for candidate in _detected_imports(node, lines)
    )
    modules = {candidate.module for candidate in matches}
    return modules.pop() if len(modules) == 1 else ""


def _import_nodes(tree: ast.Module, *, handler_only: bool) -> Iterator[_ImportNode]:
    pending: list[tuple[ast.AST, bool]] = [(tree, False)]
    while pending:
        node, in_function = pending.pop()
        if not handler_only or in_function:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                yield node
            if isinstance(node, ast.Call) and _is_dynamic_import(node.func):
                yield node
        function_body: set[ast.AST] = set()
        if handler_only and not in_function:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_body.update(node.body)
            elif isinstance(node, ast.Lambda):
                function_body.add(node.body)
        pending.extend(
            (child, in_function or child in function_body)
            for child in reversed(list(ast.iter_child_nodes(node)))
        )


def _is_dynamic_import(function: ast.expr) -> bool:
    if isinstance(function, ast.Name):
        return function.id == "__import__"
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id == "importlib"
    )


def _detected_imports(
    node: _ImportNode, lines: list[bytes]
) -> Iterator[_DetectedImport]:
    if isinstance(node, ast.Call):
        argument = next(iter(node.args), None)
        module = (
            argument.value
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            else ""
        )
        yield _DetectedImport(
            module if _valid_module(module) else "", "dynamic", _position(node, lines), ""
        )
    elif isinstance(node, ast.ImportFrom):
        position = _position(node, lines)
        if node.level:
            yield _DetectedImport("", "relative", position, "")
        else:
            candidate = _absolute_import(node.module or "", _source_fragment(node, lines), position, "import")
            if candidate.kind != "absolute":
                yield candidate
                return
            for alias in node.names:
                if (
                    _valid_module(alias.name) and "." not in alias.name
                    and _ascii_spelling(_source_fragment(alias, lines), "as")
                ):
                    yield replace(candidate, member=alias.name, position=_position(alias, lines))
                else:
                    yield replace(candidate, kind="unsupported")
    else:
        for alias in node.names:
            yield _absolute_import(
                alias.name,
                _source_fragment(alias, lines),
                _position(alias, lines),
                "as",
            )


def _absolute_import(
    module: str, fragment: str, position: SourcePosition, stop_token: str
) -> _DetectedImport:
    if _valid_module(module) and _ascii_spelling(fragment, stop_token):
        return _DetectedImport(module, "absolute", position, "")
    return _DetectedImport("", "unsupported", position, "")


def _valid_module(module: str) -> bool:
    return (
        0 < len(module) <= 120
        and bool(_MODULE_NAME.fullmatch(module))
        and not any(iskeyword(part) for part in module.split("."))
    )


def _ascii_spelling(fragment: str, stop_token: str) -> bool:
    if fragment.isascii():
        return True
    try:
        for token in generate_tokens(StringIO(fragment).readline):
            if token.string == stop_token:
                break
            if not token.string.isascii() and token.string:
                return False
    except TokenError:
        return False
    return True


def _within_source_limit(source: str) -> bool:
    return (
        len(source) <= _SOURCE_BYTE_LIMIT
        and len(source.encode("utf-8", errors="surrogatepass")) <= _SOURCE_BYTE_LIMIT
    )


def _source_lines(source: str) -> list[bytes]:
    return source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8").split(b"\n")


def _source_fragment(node: ast.ImportFrom | ast.alias, lines: list[bytes]) -> str:
    start = node.lineno - 1
    end = (node.end_lineno or node.lineno) - 1
    if start == end:
        return lines[start][node.col_offset : node.end_col_offset].decode("utf-8")
    return b"\n".join(
        (
            lines[start][node.col_offset :],
            *lines[start + 1 : end],
            lines[end][: node.end_col_offset],
        )
    ).decode("utf-8")


def _position(
    node: ast.ImportFrom | ast.alias | ast.Call, lines: list[bytes]
) -> SourcePosition:
    prefix = lines[node.lineno - 1][: node.col_offset].decode("utf-8")
    return SourcePosition(line=node.lineno, column=len(prefix) + 1)


async def _probe_import(
    session: AsyncMontySession, candidate: _DetectedImport
) -> Literal["available", "unavailable", "unverified"]:
    statement = (
        f"from {candidate.module} import {candidate.member}" if candidate.member else f"import {candidate.module}"
    )
    try:
        await session.feed_run(f"def _umbod_import_probe():\n    {statement}\n_umbod_import_probe()")
    except MontyRuntimeError as error:
        cause = error.exception()
        if isinstance(cause, ImportError):
            return "unavailable"
        if isinstance(cause, NotImplementedError):
            return "unverified"
        raise
    except MontySyntaxError:
        return "unverified"
    return "available"


def _probe_diagnostic(
    candidate: _DetectedImport, result: Literal["unavailable", "unverified"]
) -> DraftDiagnostic:
    label = (
        f"Import '{candidate.member}' from '{candidate.module}'" if candidate.member else f"Module '{candidate.module}'"
    )
    if result == "unverified":
        return _unverified(
            f"{label} could not be verified in the validation sandbox.",
            (candidate.position,),
        )
    return DraftDiagnostic(
        code="handler_import_unavailable",
        stage="handler_imports",
        severity="warning",
        message=f"{label} is unavailable in the validation sandbox.",
        action="Check that the module is supported before using this import in a handler.",
        positions=(candidate.position,),
    )


def _unverified_message(candidate: _DetectedImport) -> str:
    if candidate.kind == "relative":
        return "Relative handler import could not be verified."
    if candidate.kind == "dynamic":
        if candidate.module:
            return (
                f"Dynamic handler import of '{candidate.module}' could not be verified."
            )
        return "Dynamic handler import could not be verified."
    return "Handler import with an unsupported module name could not be verified."


def _unverified(message: str, positions: tuple[SourcePosition, ...]) -> DraftDiagnostic:
    return DraftDiagnostic(
        code="handler_import_unverified",
        stage="handler_imports",
        severity="warning",
        message=message,
        action="Use a supported absolute import to verify module availability without running the handler.",
        positions=positions,
    )
