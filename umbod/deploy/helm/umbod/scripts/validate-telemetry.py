import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def render(chart: str, values: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "values.json"
        path.write_text(json.dumps(values))
        return subprocess.run(["helm", "template", "umbod", chart, "-f", str(path)], capture_output=True, text=True, check=False)


def document(rendered: str, source: str) -> str:
    return next((item for item in rendered.split("---") if f"/templates/{source}\n" in item), "")


def main() -> None:
    chart = sys.argv[1]
    baseline = render(chart, {"ingress": {"enabled": True}})
    require(baseline.returncode == 0, baseline.stderr)
    require(not document(baseline.stdout, "telemetry.yaml"), "disabled collector must not have a service")
    require("otlp-http" not in baseline.stdout, "disabled collector must not have a port")
    require("path: /v1" not in document(baseline.stdout, "ingress.yaml"), "public ingress must not expose OTLP")
    configured_disabled = render(chart, {"ingress": {"enabled": True}, "telemetry": {"publicBaseUrl": "https://collector.example/otlp"}})
    require(configured_disabled.returncode == 0, configured_disabled.stderr)
    require(not document(configured_disabled.stdout, "telemetry.yaml"), "advertising a collector URL must not enable its service")
    require("otlp-http" not in configured_disabled.stdout, "advertising a collector URL must not enable its listener")
    require(document(configured_disabled.stdout, "ingress.yaml") == document(baseline.stdout, "ingress.yaml"), "advertising a collector URL must not expose ingestion")
    for port, service_port, public_base in ((4318, 4318, "https://collector.example/otlp"), (14318, 14319, "http://localhost:14319")):
        result = render(chart, {"ingress": {"enabled": True}, "telemetry": {"enabled": True, "publicBaseUrl": public_base, "port": port, "servicePort": service_port, "bearerTokenSecret": {"name": "collector-secret", "key": "token"}}})
        require(result.returncode == 0, result.stderr)
        core = document(result.stdout, "core-deployment.yaml")
        api, mcp = core.split("        - name: mcp\n")
        require(f"containerPort: {port}" in api and "name: otlp-http" in api, "collector must share API container")
        require('command: ["umbod", "api", "serve"]' in api, "API must own collector lifecycle")
        require(re.search(rf'name: UMBOD_OTLP_PUBLIC_BASE_URL\s+value: "{re.escape(public_base)}"', api) is not None, "API must receive the operator-declared public collector base URL")
        for key, value in (("ENABLED", "true"), ("HOST", "0.0.0.0"), ("PORT", str(port))):
            require(re.search(rf'name: UMBOD_OTLP_{key}\s+value: "{value}"', api) is not None, f"collector {key} mismatch")
        require('name: "collector-secret"' in api and 'key: "token"' in api and "secretKeyRef:" in api, "API must use dedicated token secret")
        require("UMBOD_OTLP_" not in mcp and "collector-secret" not in mcp and "otlp-http" not in mcp, "MCP must not receive collector configuration")
        service = document(result.stdout, "telemetry.yaml")
        require("kind: Deployment" not in service and "kind: PersistentVolumeClaim" not in service, "collector must not have independent deployment or storage")
        require(f"port: {service_port}" in service and "targetPort: otlp-http" in service and "type: ClusterIP" in service and "component: core" in service, "private collector service must select core pod")
        require(document(result.stdout, "ingress.yaml") == document(baseline.stdout, "ingress.yaml"), "collector must not change public ingress")
        require(result.stdout.count("kind: Deployment\n") == baseline.stdout.count("kind: Deployment\n"), "collector must not add a deployment")
        subprocess.run(["kubeconform", "-strict", "-summary"], input=result.stdout, text=True, check=True)
    invalid = [
        {"enabled": "true"}, {"enabled": True},
        *[{"publicBaseUrl": value} for value in (None, 4318, "relative", "http://collector.example", "https://user:pass@collector.example", "https://collector.example?x=1", "https://collector.example#fragment", "https://collector.example/with space")],
        {"enabled": True, "bearerTokenSecret": {"name": " "}},
        {"port": 0}, {"port": 65536}, {"servicePort": 0}, {"servicePort": 65536},
        {"bearerTokenSecret": {"key": ""}}, {"bearerTokenSecret": {"key": "bad/key"}},
        {"bearerToken": "literal"}, {"host": "0.0.0.0"},
        {"image": {}}, {"analytics": {}}, {"persistence": {}}, {"resources": {}},
    ]
    for telemetry in invalid:
        require(render(chart, {"telemetry": telemetry}).returncode != 0, f"unsafe telemetry values accepted: {telemetry}")
    for port in (8000, 8011, 8001, 8012):
        values = {"telemetry": {"enabled": True, "port": port, "bearerTokenSecret": {"name": "collector-secret"}}}
        require(render(chart, values).returncode != 0, f"collector port collision accepted: {port}")
        values["telemetry"]["enabled"] = False
        require(render(chart, values).returncode == 0, "disabled collector must not reserve its port")
    for component in ("api", "mcp"):
        for key in ("UMBOD_OTLP_ENABLED", "UMBOD_OTLP_HOST", "UMBOD_OTLP_PORT", "UMBOD_OTLP_BEARER_TOKEN", "UMBOD_OTLP_PUBLIC_BASE_URL", "UMBOD_REST_METRICS_PORT", "UMBOD_MCP_METRICS_PORT"):
            require(render(chart, {"core": {component: {"env": {key: "override"}}}}).returncode != 0, "managed listener settings must reject environment overrides")
    for component in ("api", "mcp", "frontend", "telemetry"):
        require(render(chart, {"ingress": {"paths": {component: "/v1"}}}).returncode != 0, "ingress must reject OTLP path overrides")
    for component in ("api", "mcp"):
        values = {"core": {component: {"port": 14318}}, "telemetry": {"enabled": True, "port": 14318, "bearerTokenSecret": {"name": "collector-secret"}}}
        require(render(chart, values).returncode != 0, "custom application port collision accepted")


if __name__ == "__main__":
    main()
