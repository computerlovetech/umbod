import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.request import Request, urlopen

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


@dataclass(frozen=True)
class ToolActivation:
    connector_id: str
    operation_name: str
    activation_status: str
    expected_mcp_tool_name: str


@dataclass(frozen=True)
class ConnectorState:
    connector_id: str
    publication_status: str
    tools: list[ToolActivation]


@dataclass(frozen=True)
class RuntimeCheckResult:
    api_base_url: str
    mcp_url: str
    connectors: list[ConnectorState]
    mcp_tool_names: list[str]
    expected_enabled_tool_names: list[str]
    unexpected_mcp_tool_names: list[str]
    missing_mcp_tool_names: list[str]

    @property
    def ok(self) -> bool:
        return not self.unexpected_mcp_tool_names and not self.missing_mcp_tool_names


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        check_runtime_state(
            api_base_url=args.api_base_url,
            mcp_url=args.mcp_url,
            bearer_token=args.bearer_token,
        )
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    if not result.ok:
        sys.exit(1)


async def check_runtime_state(
    api_base_url: str, mcp_url: str, bearer_token: str | None
) -> RuntimeCheckResult:
    connectors = _load_connector_states(api_base_url)
    mcp_tool_names = await _load_mcp_tool_names(mcp_url, bearer_token)
    expected_enabled_tool_names = sorted(
        tool.expected_mcp_tool_name
        for connector in connectors
        if connector.publication_status == "published"
        for tool in connector.tools
        if tool.activation_status == "enabled"
    )
    expected_set = set(expected_enabled_tool_names)
    actual_set = set(mcp_tool_names)
    return RuntimeCheckResult(
        api_base_url=api_base_url,
        mcp_url=mcp_url,
        connectors=connectors,
        mcp_tool_names=mcp_tool_names,
        expected_enabled_tool_names=expected_enabled_tool_names,
        unexpected_mcp_tool_names=sorted(actual_set - expected_set),
        missing_mcp_tool_names=sorted(expected_set - actual_set),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", default="http://localhost:18010")
    parser.add_argument("--mcp-url", default="http://localhost:8011/mcp")
    parser.add_argument(
        "--bearer-token",
        default="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJsb2NhbC10ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3QtdXNlckBleGFtcGxlLmNvbSIsIm5hbWUiOiJMb2NhbCBUZXN0IFVzZXIiLCJncm91cHMiOlsidGVzdCJdfQ.",
    )
    return parser.parse_args()


def _load_connector_states(api_base_url: str) -> list[ConnectorState]:
    connectors_payload = _get_json(f"{api_base_url.rstrip('/')}/admin/connectors/catalog")
    connectors: list[ConnectorState] = []
    for connector in connectors_payload["connectors"]:
        connector_id = connector["id"]
        tools_payload = _get_json(
            f"{api_base_url.rstrip('/')}/admin/connectors/catalog/{connector_id}/tools"
        )
        connectors.append(
            ConnectorState(
                connector_id=connector_id,
                publication_status=connector["publication_status"],
                tools=[
                    ToolActivation(
                        connector_id=connector_id,
                        operation_name=tool["operation_name"],
                        activation_status=tool["activation_status"],
                        expected_mcp_tool_name=_mangle_tool_name(
                            connector_id, tool["operation_name"]
                        ),
                    )
                    for tool in tools_payload["tools"]
                ],
            )
        )
    return connectors


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def _load_mcp_tool_names(mcp_url: str, bearer_token: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    transport = StreamableHttpTransport(mcp_url, headers=headers)
    async with Client(transport) as client:
        tools = await client.list_tools()
    return sorted(tool.name for tool in tools)


def _mangle_tool_name(connector_id: str, operation_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{connector_id}_{operation_name}").strip("_")


if __name__ == "__main__":
    main()
