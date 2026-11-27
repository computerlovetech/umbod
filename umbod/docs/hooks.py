import json
import re
from pathlib import Path
from typing import Any

import yaml
from mkdocs.config.defaults import MkDocsConfig

RELEASE_FIELDS = ("chartVersion", "imageTag", "sdkVersion")
RELEASE_TOKEN = re.compile(r"\{\{\s*release\.([A-Za-z]+)\s*\}\}")

# Agent-readable output: each page is also published as Markdown next to its HTML,
# with llms.txt as the index and llms-full.txt as the whole site in one file.
_nav_order: list[str] = []
_rendered_pages: dict[str, tuple[str, str, str]] = {}


VALUE_SECTIONS = {
    "nameOverride": ("Chart name override", "Override the chart name used to name Kubernetes resources."),
    "fullnameOverride": ("Full resource name override", "Set the full name used for chart-created Kubernetes resources."),
    "imagePullSecrets": ("Image pull secrets", "Provide credentials for pulling images from private registries."),
    "serviceAccount": ("Service account", "Control the service account created for the workloads and whether its token is mounted."),
    "existingSecret": ("Application secret", "Name the existing Kubernetes Secret that supplies application credentials."),
    "config": ("Application configuration", "Set the runtime profile, logging, authentication, authorization, public origins, features, and analytics backend."),
    "plugins": ("Connector plugins", "Configure available connectors and their deployment image and resources."),
    "core": ("Core API and MCP workloads", "Configure the shared core image and the API and MCP containers."),
    "telemetry": ("Private telemetry collector", "Configure the private collector listener, advertised client URL, service port, and bearer-token secret."),
    "frontend": ("Frontend workload", "Configure the web frontend image, replicas, environment, and resources."),
    "persistence": ("Persistent storage", "Configure the optional persistent volume claim used for SQLite data."),
    "services": ("Kubernetes services", "Set the service ports exposed for the API, MCP, and frontend workloads."),
    "ingress": ("Ingress", "Configure external hosts, TLS, and paths that route traffic to the services."),
    "podAnnotations": ("Pod annotations", "Attach annotations to the chart-managed pods."),
    "podLabels": ("Pod labels", "Attach additional labels to the chart-managed pods."),
    "nodeSelector": ("Node selection", "Select the nodes on which the workloads may run."),
    "tolerations": ("Pod tolerations", "Allow workloads to run on nodes with matching taints."),
    "affinity": ("Pod affinity", "Control placement of workloads relative to nodes or other pods."),
}


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


def _release_metadata(app_directory: Path) -> dict[str, str]:
    metadata = json.loads((app_directory.parent / "release-metadata.json").read_text())
    if not isinstance(metadata, dict) or set(metadata) != set(RELEASE_FIELDS):
        raise ValueError("release-metadata.json must define chartVersion, imageTag, and sdkVersion")
    if any(not isinstance(metadata[field], str) or not metadata[field] for field in RELEASE_FIELDS):
        raise ValueError("release-metadata.json versions must be nonempty strings")
    return metadata


def on_page_markdown(markdown: str, **kwargs: Any) -> str:
    app_directory = Path(kwargs["config"].config_file_path).parent
    metadata = _release_metadata(app_directory)

    def replace_token(match: re.Match[str]) -> str:
        field = match.group(1)
        if field not in metadata:
            raise ValueError(f"Unknown release metadata field: {field}")
        return metadata[field]

    rendered = RELEASE_TOKEN.sub(replace_token, markdown)
    page = kwargs["page"]
    _rendered_pages[page.file.src_uri] = (page.title, str(page.meta.get("description", "")), rendered)
    return rendered


def on_nav(nav: Any, **kwargs: Any) -> Any:
    _nav_order[:] = [page.file.src_uri for page in nav.pages]
    return nav


def on_post_build(config: MkDocsConfig, **kwargs: Any) -> None:
    site_directory = Path(config.site_dir)
    index = [f"# {config.site_name}", "", f"> {config.site_description}", "", "## Pages", ""]
    full: list[str] = []
    for src_uri in _nav_order:
        title, description, markdown = _rendered_pages[src_uri]
        target = site_directory / src_uri
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown.strip() + "\n")
        index.append(f"- [{title}]({src_uri}): {description}" if description else f"- [{title}]({src_uri})")
        full.append(markdown.strip())
    (site_directory / "llms.txt").write_text("\n".join(index) + "\n")
    (site_directory / "llms-full.txt").write_text("\n\n---\n\n".join(full) + "\n")


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    app_directory = Path(config.config_file_path).parent
    release = _release_metadata(app_directory)
    chart_directory = app_directory / "deploy" / "helm" / "umbod"
    values_path = chart_directory / "values.yaml"
    schema_path = chart_directory / "values.schema.json"
    values_text = values_path.read_text()
    values = yaml.safe_load(values_text)
    schema = json.loads(schema_path.read_text())
    sections: list[str] = []
    for key, value in values.items():
        title, description = VALUE_SECTIONS[key]
        sections.extend(
            [
                f"## {title} (`{key}`)",
                "",
                description,
                "",
                "| Value | Type | Default | Constraints |",
                "| --- | --- | --- | --- |",
                *_reference_rows({key: value}, schema, schema.get("definitions", {})),
                "",
            ]
        )
    content = "\n".join(
        [
            "---",
            "description: Every Umbod Helm chart value with its type, default, and constraints.",
            "---",
            "",
            "# Helm values",
            "",
            f"Defaults for the chart in the repository. For the published chart `{release['chartVersion']}`, which pins images `{release['imageTag']}`, run:",
            "",
            "```bash",
            f"helm show values oci://ghcr.io/computerlovetech/charts/umbod --version {release['chartVersion']}",
            "```",
            "",
            *sections,
        ]
    )
    output_path = app_directory / "docs" / "reference" / "helm-values.md"
    output_path.write_text(content)
    return config
