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


def configured(hosting: str, enabled: bool, port: int = 8013) -> dict[str, Any]:
    return {"core": {"mcp": {"administrator": {"hosting": hosting, "port": port, "baseUrl": "https://admin.example"}}}, "config": {"features": {"mcp": {"administratorEnabled": enabled}}}, "ingress": {"enabled": True}}


def main() -> None:
    chart = sys.argv[1]
    baseline = render(chart, {"ingress": {"enabled": True}})
    require(baseline.returncode == 0, baseline.stderr)
    baseline_ingress = next(item for item in baseline.stdout.split("---") if "/templates/ingress.yaml" in item)
    for hosting in ("shared", "separate"):
        for enabled in (False, True):
            for port in (8013, 18013):
                result = render(chart, configured(hosting, enabled, port))
                require(result.returncode == 0, result.stderr)
                active = hosting == "separate" and enabled
                require(("targetPort: mcp-admin" in result.stdout) == active, "administrator service must require enabled separate hosting")
                core = next(item for item in result.stdout.split("---") if "/templates/core-deployment.yaml" in item)
                api, mcp = core.split("        - name: mcp\n")
                require("name: mcp-admin" not in api, "API must not host administrator MCP")
                require((f"containerPort: {port}" in mcp) == active, "administrator port must exist only on active MCP container")
                for key, value in (("HOSTING", hosting), ("HOST", "0.0.0.0"), ("PORT", str(port)), ("BASE_URL", "https://admin.example")):
                    for container in (api, mcp):
                        require(re.search(rf'name: UMBOD_MCP_ADMINISTRATOR_{key}\s+value: "{re.escape(value)}"', container) is not None, f"administrator {key} mismatch")
                ingress = next(item for item in result.stdout.split("---") if "/templates/ingress.yaml" in item)
                require(ingress == baseline_ingress, "administrator must not change public ingress")
                if active:
                    service = next(item for item in result.stdout.split("---") if "/templates/mcp-administrator.yaml" in item)
                    require("type: ClusterIP" in service and "component: core" in service and f"port: {port}" in service, "administrator service must privately select core")
                subprocess.run(["kubeconform", "-strict", "-summary"], input=result.stdout, text=True, check=True)
    custom = render(chart, {"core": {"api": {"port": 18000}, "mcp": {"port": 18011}}})
    require(custom.returncode == 0, custom.stderr)
    core = next(item for item in custom.stdout.split("---") if "/templates/core-deployment.yaml" in item)
    for container in core.split("        - name: mcp\n"):
        for key, port in (("REST", 18000), ("MCP", 18011)):
            require(re.search(rf'name: UMBOD_{key}_PORT\s+value: "{port}"', container) is not None, "both containers must receive actual application ports")
    for port in (8000, 8011, 8001, 8012, 14318):
        values = configured("separate", True, port)
        values["telemetry"] = {"enabled": True, "port": 14318, "bearerTokenSecret": {"name": "collector-secret"}}
        require(render(chart, values).returncode != 0, f"administrator collision accepted: {port}")
        values["config"]["features"]["mcp"]["administratorEnabled"] = False
        require(render(chart, values).returncode == 0, "disabled administrator must not reserve a port")
    for component in ("api", "mcp"):
        values = configured("separate", True, 18013)
        values["core"].setdefault(component, {})["port"] = 18013
        require(render(chart, values).returncode != 0, "custom application port collision accepted")
        for key in ("UMBOD_REST_PORT", "UMBOD_MCP_PORT"):
            require(render(chart, {"core": {component: {"env": {key: "18013"}}}}).returncode != 0, "managed application port override accepted")
        for key in ("HOSTING", "HOST", "PORT", "BASE_URL"):
            require(render(chart, {"core": {component: {"env": {f"UMBOD_MCP_ADMINISTRATOR_{key}": "override"}}}}).returncode != 0, "managed administrator environment override accepted")
        require(render(chart, {"core": {component: {"env": {"UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED": False}}}}).returncode != 0, "feature override must use typed configuration")
    for administrator in ({"hosting": "unknown"}, {"port": "8013"}, {"host": "127.0.0.1"}, {"enabled": True}):
        require(render(chart, {"core": {"mcp": {"administrator": administrator}}}).returncode != 0, f"invalid administrator settings accepted: {administrator}")
    invalid_origins = ("", "relative", "https://user:pass@admin.example", "https://admin.example/private", "https://admin.example//", "https://admin.example?query", "https://admin.example#fragment", "http://admin.example", "http://192.168.1.1", "http://[::2]", "https://-invalid.example", "https://bad_host.example", "https://[:::1]", "https://admin.example:0", "https://admin.example:65536", "https://admin.example:abc", "https://admin.example:", "https://admin.example\\\\path", "https://admin.example\n")
    for administrator in ({"port": 0}, {"port": 65536}, *({"baseUrl": origin} for origin in invalid_origins)):
        for hosting, enabled in (("separate", True), ("shared", True), ("separate", False)):
            values = configured(hosting, enabled)
            values["core"]["mcp"]["administrator"].update(administrator)
            result = render(chart, values)
            require((result.returncode != 0) == (hosting == "separate" and enabled), f"dedicated validation must apply only when active: {administrator}, {hosting}, {enabled}: {result.stderr}")
    for origin in ("https://admin.example", "https://admin.example/", "https://admin.example:65535", "https://[2001:db8::1]:8013", "http://localhost:8013", "http://127.0.0.1:8013/", "http://127.12.34.56", "http://[::1]:8013", "http://[0:0:0:0:0:0:0:1]"):
        values = configured("separate", True)
        values["core"]["mcp"]["administrator"]["baseUrl"] = origin
        result = render(chart, values)
        require(result.returncode == 0, f"valid administrator origin rejected: {origin}: {result.stderr}")
    require("targetPort: mcp-admin" in baseline.stdout, "default separate hosting must expose the private administrator service")
    core = next(item for item in baseline.stdout.split("---") if "/templates/core-deployment.yaml" in item)
    api, mcp = core.split("        - name: mcp\n")
    require("name: mcp-admin" not in api, "default API must not host administrator MCP")
    require("containerPort: 8013" in mcp, "default administrator listener must use port 8013")


if __name__ == "__main__":
    main()
