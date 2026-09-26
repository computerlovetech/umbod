import os
from urllib.request import Request, urlopen


def put_json(url: str, payload: bytes) -> None:
    request = Request(url, data=payload, method="PUT", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Bootstrap request failed: {url} ({response.status})")


def main() -> None:
    api_base_url = os.environ["UMBOD_TEST_API_BASE_URL"]
    connector_url = f"{api_base_url}/admin/connectors/catalog/test"
    put_json(f"{connector_url}/configuration", b'{"configuration":{"instance_name":"Kind"}}')
    put_json(f"{connector_url}/publication", b"{}")


if __name__ == "__main__":
    main()
