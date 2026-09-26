import os
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class RuntimeEndpoints:
    api_base_url: str
    mcp_url: str
    bearer_token: str


@pytest.fixture(scope="session")
def runtime_endpoints() -> RuntimeEndpoints:
    return RuntimeEndpoints(
        api_base_url=os.environ.get("UMBOD_TEST_API_BASE_URL", "http://localhost:18010"),
        mcp_url=os.environ.get("UMBOD_TEST_MCP_URL", "http://localhost:8011/mcp"),
        bearer_token=os.environ.get(
            "UMBOD_TEST_BEARER_TOKEN",
            "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJsb2NhbC10ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3QtdXNlckBleGFtcGxlLmNvbSIsIm5hbWUiOiJMb2NhbCBUZXN0IFVzZXIiLCJncm91cHMiOlsidGVzdCJdfQ.",
        ),
    )
