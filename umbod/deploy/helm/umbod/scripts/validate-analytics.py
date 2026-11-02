import json
import re
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate_analytics(rendered: str, enabled: str, sqlite_path: str) -> None:
    containers = dict(re.findall(
        r"^        - name: (api|mcp)\n(.*?)(?=^        - name: |^      volumes:|\Z)",
        rendered,
        flags=re.MULTILINE | re.DOTALL,
    ))
    require(set(containers) == {"api", "mcp"}, "Expected API and MCP containers")
    expected = {
        "UMBOD_TELEMETRY_ANALYTICS_ENABLED": enabled,
        "UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH": sqlite_path,
    }
    for variable, value in expected.items():
        pattern = rf"^\s+- name: {variable}\n\s+value: ([^\n]+)$"
        matches = re.findall(pattern, containers["api"], flags=re.MULTILINE)
        require(len(matches) == 1, f"API must configure {variable} exactly once")
        require(json.loads(matches[0]) == value, f"Unexpected effective {variable}")
        require(f"name: {variable}\n" not in containers["mcp"], f"MCP must not configure {variable}")
        require(rendered.count(f"name: {variable}\n") == 1, f"Only API may configure {variable}")
    require("mountPath: /app/data" in containers["api"], "Analytics storage must use the API data mount")


def main() -> None:
    validate_analytics(Path(sys.argv[1]).read_text(), sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
