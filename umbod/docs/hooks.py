import json
from pathlib import Path
from typing import Any

import yaml
from mkdocs.config.defaults import MkDocsConfig


def _merge_mappings(base: dict[str, Any], addition: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in addition.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_mappings(current, value)
        else:
            merged[key] = value
    return merged


def _merge_schema(schema: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    reference = schema.get("$ref")
    if isinstance(reference, str):
        resolved = _merge_mappings(resolved, definitions[reference.rsplit("/", maxsplit=1)[-1]])
    for part in schema.get("allOf", []):
        resolved = _merge_mappings(resolved, _merge_schema(part, definitions))
    return _merge_mappings(resolved, {key: value for key, value in schema.items() if key not in {"$ref", "allOf"}})


def _constraint_text(schema: dict[str, Any]) -> str:
    constraint_keys = ("const", "enum", "minimum", "maximum", "minLength", "minItems", "uniqueItems")
    constraints = [f"{key}: {json.dumps(schema[key], separators=(',', ':'))}" for key in constraint_keys if key in schema]
    return ", ".join(constraints) or "—"


def _value_text(value: Any) -> str:
    rendered = json.dumps(value, separators=(",", ":"))
    return rendered.replace("|", "\\|")


def _type_text(value: Any, schema: dict[str, Any]) -> str:
    inferred_types = {bool: "boolean", dict: "object", int: "integer", list: "array", str: "string"}
    return str(schema.get("type", inferred_types.get(type(value), type(value).__name__)))


def _reference_rows(
    values: dict[str, Any],
    schema: dict[str, Any],
    definitions: dict[str, Any],
    prefix: str = "",
) -> list[str]:
    rows: list[str] = []
    resolved_schema = _merge_schema(schema, definitions)
    properties = resolved_schema.get("properties", {})
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        property_schema = _merge_schema(properties.get(key, {}), definitions)
        if isinstance(value, dict) and value:
            rows.extend(_reference_rows(value, property_schema, definitions, path))
            continue
        value_type = _type_text(value, property_schema)
        rows.append(f"| `{path}` | `{value_type}` | `{_value_text(value)}` | {_constraint_text(property_schema)} |")
    return rows


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    app_directory = Path(config.config_file_path).parent
    chart_directory = app_directory / "deploy" / "helm" / "umbod"
    values_path = chart_directory / "values.yaml"
    schema_path = chart_directory / "values.schema.json"
    chart_path = chart_directory / "Chart.yaml"
    values_text = values_path.read_text()
    values = yaml.safe_load(values_text)
    schema = json.loads(schema_path.read_text())
    chart = yaml.safe_load(chart_path.read_text())
    rows = _reference_rows(values, schema, schema.get("definitions", {}))
    content = "\n".join(
        [
            "# Helm values reference",
            "",
            f"This reference is generated from the defaults and schema shipped with Umbod chart `{chart['version']}`.",
            "",
            "Inspect the released chart directly:",
            "",
            "```bash",
            f"helm show values oci://ghcr.io/computerlovetech/charts/umbod --version {chart['version']}",
            "```",
            "",
            "## Values",
            "",
            "| Value | Type | Default | Constraints |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            "## Complete defaults",
            "",
            "```yaml",
            values_text.rstrip(),
            "```",
            "",
        ]
    )
    output_path = app_directory / "docs" / "reference" / "helm-values.md"
    output_path.write_text(content)
    return config
