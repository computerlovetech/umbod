from __future__ import annotations

import ast
from pathlib import PurePosixPath
from textwrap import dedent
from typing import NamedTuple, Optional


class BoundaryViolation(NamedTuple):
    path: str
    line: int
    reason: str


PHYSICAL_FILES = frozenset({
    "persistence_runtime.py",
    "support/persistence_processes.py",
    "umbod/hosting/integration/test_api_server_process.py",
})
IMPORT_ONLY_FILE = "umbod/core/persistence/test_driver_package_imports.py"
PHYSICAL_FIXTURES = frozenset({
    "prepared_connector_store_database", "isolated_connector_store_database",
})


def qualified_name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{qualified_name(node.value, aliases)}.{node.attr}"
    return ""


def literal(node: Optional[ast.AST]) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def dictionary(node: ast.AST) -> dict[str, ast.AST]:
    if not isinstance(node, ast.Dict):
        return {}
    return {
        str(literal(key)): value
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(literal(key), str)
    }


def backend_name(name: str) -> bool:
    parts = name.lower().split(".")
    return any(part in {"sqlite", "sqlite3", "aiosqlite"} for part in parts)


def backend_factory(name: str) -> bool:
    tail = name.rsplit(".", 1)[-1].lower()
    return (
        ("sqlite" in tail and tail.startswith(("create_", "prepared_", "prepare_")))
        or (tail.startswith("sqlite") and tail.endswith(("database", "connection", "driver")))
        or (backend_name(name) and tail in {"connect", "connection", "database"})
    )


def registry_name(name: str) -> bool:
    return (
        name == "DATABASE_ADAPTERS"
        or name.endswith(".DATABASE_ADAPTERS")
        or name.startswith("tests.umbod.infrastructure.persistence.adapters")
        or name.startswith("umbod.infrastructure.persistence.adapters")
    )


def environment_reason(key: object, value: object) -> str:
    if not isinstance(key, str):
        return ""
    normalized = key.upper()
    if normalized.startswith("UMBOD_") and "SQLITE" in normalized and "PATH" in normalized:
        return "SQLite path environment"
    if normalized == "UMBOD_CONNECTOR_STORE" and str(value).lower() == "sqlite":
        return "SQLite connector environment"
    if normalized == "UMBOD_TELEMETRY_ANALYTICS_ENABLED" and str(value).lower() in {"true", "1"}:
        return "SQLite analytics environment"
    return ""


def configuration_reason(node: ast.Call, name: str) -> str:
    tail = name.rsplit(".", 1)[-1]
    keywords = {item.arg: item.value for item in node.keywords if item.arg is not None}
    if tail in {"model_validate", "model_construct", "model_copy"}:
        tail = name.rsplit(".", 2)[-2]
        payload = node.args[0] if node.args else keywords.get("update", keywords.get("obj"))
        if payload is not None:
            keywords.update(dictionary(payload))
    reason = fields_reason(keywords)
    if reason:
        return reason
    if tail.lower() == "sqliteconnectorstoreconfig":
        return "SQLite connector configuration"
    if "config" in name.lower() and "sqlite_path" in keywords:
        return "SQLite path configuration"
    if tail == "ConnectorStoreConfig" and str(literal(keywords.get("type"))).lower() == "sqlite":
        return "SQLite connector configuration"
    if tail in {"TelemetryAnalyticsConfig", "telemetry_analytics"} and literal(keywords.get("enabled")) in (True, 1):
        return "SQLite analytics configuration"
    return ""


def configuration_assignment_reason(target: ast.Attribute, value: ast.AST, aliases: dict[str, str]) -> str:
    owner = qualified_name(target.value, aliases).rsplit(".", 1)[-1]
    if target.attr == "enabled" and owner in {"TelemetryAnalyticsConfig", "telemetry_analytics"}:
        if literal(value) in (True, 1):
            return "SQLite analytics configuration mutation"
    if target.attr == "type" and owner in {"ConnectorStoreConfig", "connector_store"}:
        if str(literal(value)).lower() == "sqlite":
            return "SQLite connector configuration mutation"
    return ""


def fields_reason(fields: dict[str, ast.AST]) -> str:
    for key, value in fields.items():
        reason = environment_reason(key, literal(value))
        if reason:
            return reason
    connector = fields.get("connector_store")
    if connector is not None and str(literal(dictionary(connector).get("type"))).lower() == "sqlite":
        return "SQLite connector configuration payload"
    telemetry = fields.get("telemetry")
    analytics = fields.get("telemetry_analytics", fields.get("analytics"))
    if telemetry is not None:
        analytics = dictionary(telemetry).get("analytics", analytics)
    if analytics is not None and literal(dictionary(analytics).get("enabled")) in (True, 1):
        return "SQLite analytics configuration payload"
    return ""


def embedded_programs(tree: ast.Module, aliases: dict[str, str]) -> list[ast.AST]:
    programs: list[ast.AST] = []
    assigned = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in {"program", "script", "code", "python_code"} for target in targets):
                if node.value is not None:
                    programs.append(node.value)
        if isinstance(node, ast.Call) and qualified_name(node.func, aliases).startswith("subprocess."):
            for argument in node.args:
                if isinstance(argument, (ast.List, ast.Tuple)):
                    for index, item in enumerate(argument.elts[:-1]):
                        if literal(item) == "-c":
                            candidate = argument.elts[index + 1]
                            if isinstance(candidate, ast.Name):
                                candidate = assigned.get(candidate.id, candidate)
                            programs.append(candidate)
    return programs


def source_text(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(str(part.value) if isinstance(part, ast.Constant) else "embedded_value" for part in node.values)
    if isinstance(node, ast.Call):
        wrapper = qualified_name(node.func, aliases).rsplit(".", 1)[-1]
        if wrapper == "dedent" and node.args:
            return source_text(node.args[0], aliases)
        if wrapper == "strip" and isinstance(node.func, ast.Attribute):
            return source_text(node.func.value, aliases)
    return ""


def import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        if isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module or ''}.{item.name}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is None:
                continue
            name = qualified_name(node.value, aliases)
            if isinstance(node.value, ast.Call):
                constructor = qualified_name(node.value.func, aliases)
                if constructor.rsplit(".", 1)[-1].endswith("Config"):
                    name = constructor
                elif constructor.rsplit(".", 1)[-1] in {"model_validate", "model_construct", "model_copy"}:
                    name = constructor.rsplit(".", 1)[0]
            if name:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = name
    return aliases


def node_reasons(node: ast.AST, aliases: dict[str, str], config_allowed: bool, imports_allowed: bool) -> list[str]:
    reasons: list[str] = []
    imported: list[str] = []
    if isinstance(node, ast.Import):
        imported = [item.name for item in node.names]
    if isinstance(node, ast.ImportFrom):
        imported = [f"{node.module or ''}.{item.name}" for item in node.names]
    for name in imported:
        if registry_name(name):
            reasons.append("physical database adapter registry import")
        if not imports_allowed and (backend_name(name) or backend_factory(name)):
            reasons.append("SQLite backend import")
    if isinstance(node, ast.Call):
        name = qualified_name(node.func, aliases)
        if backend_factory(name):
            reasons.append("SQLite database factory or connection")
        if config_allowed and name.rsplit(".", 1)[-1] in {
            "create_configured_analytics_runtime", "ConfiguredPersistenceRuntimeProvider",
        }:
            reasons.append("configuration policy must not construct persistence runtimes")
        if registry_name(name):
            reasons.append("physical database adapter registry call")
        if name.endswith("import_module") or name == "__import__":
            if node.args and backend_name(str(literal(node.args[0]))) and not imports_allowed:
                reasons.append("SQLite dynamic backend import")
        if not config_allowed:
            reason = configuration_reason(node, name)
            if reason:
                reasons.append(reason)
            environment_args = node.args
            if name.endswith(".setitem") and node.args and qualified_name(node.args[0], aliases) == "os.environ":
                environment_args = node.args[1:]
            if name.endswith((".setenv", ".setitem")) and len(environment_args) >= 2:
                reason = environment_reason(literal(environment_args[0]), literal(environment_args[1]))
                if reason:
                    reasons.append(reason)
    if not config_allowed:
        if isinstance(node, ast.Dict):
            reason = fields_reason(dictionary(node))
            if reason:
                reasons.append(reason)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    reason = configuration_assignment_reason(target, node.value, aliases)
                    if reason:
                        reasons.append(reason)
                if isinstance(target, ast.Subscript) and qualified_name(target.value, aliases) == "os.environ":
                    reason = environment_reason(literal(target.slice), literal(node.value))
                    if reason:
                        reasons.append(reason)
        if isinstance(node, ast.Attribute) and node.attr == "sqlite_path":
            reasons.append("SQLite configuration path reference")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if any(argument.arg in PHYSICAL_FIXTURES for argument in arguments):
                reasons.append("physical connector database fixture")
    return reasons


def scan_sqlite_boundaries(source: str, relative_path: str) -> tuple[BoundaryViolation, ...]:
    path = PurePosixPath(relative_path).as_posix()
    if path.startswith("tests/"):
        path = path[len("tests/"):]
    if path in PHYSICAL_FILES or path.startswith("umbod/infrastructure/"):
        return ()
    tree = ast.parse(source, filename=path)
    aliases = import_aliases(tree)
    config_allowed = path.startswith("umbod/config/")
    imports_allowed = path == IMPORT_ONLY_FILE
    violations = [
        BoundaryViolation(path, node.lineno, reason)
        for node in ast.walk(tree)
        for reason in node_reasons(node, aliases, config_allowed, imports_allowed)
    ]
    for program in embedded_programs(tree, aliases):
        text = source_text(program, aliases)
        if not text:
            continue
        try:
            embedded = ast.parse(dedent(text))
        except (SyntaxError, ValueError):
            continue
        embedded_aliases = import_aliases(embedded)
        violations.extend(
            BoundaryViolation(path, program.lineno + node.lineno - 1, f"embedded Python: {reason}")
            for node in ast.walk(embedded)
            for reason in node_reasons(node, embedded_aliases, config_allowed, imports_allowed)
        )
    return tuple(sorted(set(violations)))
