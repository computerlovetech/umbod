from pathlib import Path
import re
import sys


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate_core(core: str) -> None:
    require("replicas: 1" in core and "type: Recreate" in core, "core must be one replica with Recreate strategy")
    require(core.count("mountPath: /app/data") == 2, "API and MCP must both mount /app/data")
    require(core.count('mountPath: "/app/config/connector-deployment-availability.json"') == 2, "API and MCP must mount connector availability")
    require(core.count("subPath: connector-deployment-availability.json") == 2, "API and MCP must mount the generated availability file")
    require("checksum/connector-availability:" in core, "connector availability changes must trigger a rollout")
    require(core.count("claimName:") == 1, "core must use one PVC")
    require(core.count("name: metrics") == 2, "API and MCP must each declare a metrics port")
    require("containerPort: 8001" in core, "API metrics port 8001 must be declared")
    require("containerPort: 8012" in core, "MCP metrics port 8012 must be declared")
    require(core.count("startupProbe:") == 2, "API and MCP must have startup probes")
    require(core.count('image: "ghcr.io/computerlovetech/umbod:ci"') == 3, "API, MCP, and plugin validation must use the shared core image")
    require(core.count('image: "ghcr.io/computerlovetech/umbod-plugins:ci"') == 1, "core Pod must initialize plugins from the configured image")
    require('command: ["umbod", "connectors", "validate", "--plugin-path", "/plugins"]' in core, "core must validate plugins before application startup")
    require(core.count("name: connector-plugins") == 6, "plugin volume must connect both init containers, API, MCP, and the Pod specifications")
    require(core.count("mountPath: /plugins") == 4, "plugin initialization, validation, API, and MCP must mount /plugins")
    require(core.count("readOnly: true") == 5, "plugin validator and API/MCP plugin and availability mounts must be read-only")
    require(core.count("name: PYTHONPATH") == 2, "API and MCP must configure plugin imports")
    require(core.count("value: /plugins") == 2, "API and MCP must use the shared plugin path")
    require(core.count("emptyDir: {}") == 1, "core Pod must use one ephemeral plugin volume")
    require('command: ["umbod", "api", "serve"]' in core, "API must use the API CLI command")
    require('command: ["umbod", "mcp", "serve"]' in core, "MCP must use the MCP CLI command")
    require(core.count("name: UMBOD_DATA_DIR") == 2, "API and MCP must configure the data directory")
    require(core.count("name: UMBOD_CONNECTOR_STORE") == 2, "API and MCP must configure SQLite persistence")
    require(core.count("name: UMBOD_MCP_MESSAGING_TRANSPORT") == 2, "API and MCP must configure SQL messaging")
    require(core.count("name: UMBOD_INTERNAL_API_ORIGIN\n              value: http://127.0.0.1:8000") == 2, "core containers must reach their colocated API without requiring Pod readiness")
    require("name: UMBOD_REST_METRICS_PORT\n              value: \"8001\"" in core, "API metrics environment is required")
    require("name: UMBOD_MCP_METRICS_PORT\n              value: \"8012\"" in core, "MCP metrics environment is required")


def validate_frontend(frontend: str) -> None:
    require("mountPath: /app/data" not in frontend, "frontend must not mount the data PVC")
    require(frontend.count("startupProbe:") == 1, "frontend must have a startup probe")
    require(frontend.count("name: Host\n                  value: frontend") == 3, "frontend health probes must use the internal health host")
    require("name: PRIVATE_API_BASE_URL" in frontend, "frontend must configure its internal API URL")
    require(re.search(r"value: http://[a-z0-9-]+-api:8000", frontend) is not None, "frontend internal API URL must use the API Service")
    variables = ["ORIGIN", "PROTOCOL_HEADER", "HOST_HEADER", "PUBLIC_MCP_BASE_URL", "BODY_SIZE_LIMIT", "PRIVATE_AUTH_TOKEN_HEADER", "UMBOD_LOG_LEVEL"]
    for variable in variables:
        require(f"name: {variable}" in frontend, f"frontend must configure {variable}")


def validate_ingress(ingress: str) -> None:
    mcp_service_name = re.search(r"name: ([a-z0-9-]+-mcp)", ingress)
    require(mcp_service_name is not None, "Ingress must route to the MCP Service")
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/authorize",
        "/token",
        "/register",
        "/revoke",
    ):
        route = re.search(
            rf"- path: {re.escape(path)}\n(?:(?!          - path:).)*?name: {re.escape(mcp_service_name.group(1))}",
            ingress,
            re.DOTALL,
        )
        require(route is not None, f"Ingress path {path} must route to the MCP Service")


def main() -> None:
    rendered = Path(sys.argv[1]).read_text()
    documents = [document for document in re.split(r"^---\s*$", rendered, flags=re.MULTILINE) if "kind:" in document]
    deployments = [document for document in documents if re.search(r"^kind: Deployment$", document, re.MULTILINE)]
    services = [document for document in documents if re.search(r"^kind: Service$", document, re.MULTILINE)]
    secrets = [document for document in documents if re.search(r"^kind: Secret$", document, re.MULTILINE)]
    config_maps = [document for document in documents if re.search(r"^kind: ConfigMap$", document, re.MULTILINE)]
    core = next((document for document in deployments if "app.kubernetes.io/component: core" in document), "")
    frontend = next((document for document in deployments if "app.kubernetes.io/component: frontend" in document), "")
    ingress = next((document for document in documents if re.search(r"^kind: Ingress$", document, re.MULTILINE)), "")
    helm_tests = [document for document in documents if '"helm.sh/hook": test' in document]
    require(len(deployments) == 2, "expected exactly two Deployments")
    require(len(services) == 3, "expected exactly three Services")
    require(not secrets, "chart must not render Secrets")
    require(all("type: ClusterIP" in service for service in services), "all Services must be ClusterIP")
    require("apiVersion: networking.k8s.io/v1\nkind: Ingress" in rendered, "CI render must include a v1 Ingress")
    require(len(config_maps) == 1, "expected exactly one connector availability ConfigMap")
    require('connector-deployment-availability.json: "{\\"connectors\\":[{\\"id\\":\\"test\\"},{\\"id\\":\\"rejseplanen\\"}]}"' in config_maps[0], "connector availability ConfigMap must use the runtime JSON contract")
    require(len(helm_tests) == 3, "chart must render service health, authorization discovery, and plugin availability tests")
    require("/.well-known/oauth-protected-resource/mcp" in "\n".join(helm_tests), "Helm tests must verify protected resource discovery")
    require("/admin/connectors/catalog" in "\n".join(helm_tests), "Helm tests must verify selected installed plugins")
    require("envFrom:" in core and "envFrom:" in frontend, "existing Secret must be consumed through envFrom")
    require(":latest" not in rendered, "rendered images must not use the latest tag")
    validate_core(core)
    validate_frontend(frontend)
    validate_ingress(ingress)


if __name__ == "__main__":
    main()
