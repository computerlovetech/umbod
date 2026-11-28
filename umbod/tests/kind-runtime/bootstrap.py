import os
from urllib.request import Request, urlopen


def send_json(url: str, payload: bytes, method: str) -> None:
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Bootstrap request failed: {url} ({response.status})")


def put_json(url: str, payload: bytes) -> None:
    send_json(url, payload, "PUT")


def seed_signed_group_mappings(api_base_url: str) -> None:
    send_json(
        f"{api_base_url}/api/admin/system-settings/provider-group-mappings",
        b'{"operation":"set","mappings":[{"external_value":"admin","group_id":"admin"}]}',
        "PATCH",
    )


def main() -> None:
    api_base_url = os.environ["UMBOD_TEST_API_BASE_URL"]
    connector_url = f"{api_base_url}/api/admin/connectors/catalog/test"
    put_json(f"{connector_url}/configuration", b'{"configuration":{"instance_name":"Kind"}}')
    put_json(f"{connector_url}/publication", b"{}")
    put_json(
        f"{connector_url}/tools/activation",
        b'{"tools":[{"tool_id":"echo","activation_status":"enabled"}]}',
    )
    put_json(
        f"{api_base_url}/api/admin/mcp-permissions/groups/admin/permissions",
        b'{"capabilities":[{"connector_id":"test","capability_kind":"tool",'
        b'"capability_key":"echo","permission_status":"enabled"}]}',
    )


if __name__ == "__main__":
    main()
