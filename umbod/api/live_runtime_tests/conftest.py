import os
from dataclasses import dataclass, field

import pytest


@dataclass(frozen=True)
class RuntimeEndpoints:
    api_base_url: str
    otlp_base_url: str
    mcp_url: str
    bearer_token: str = field(repr=False)


@pytest.fixture(scope="session")
def otlp_bearer_token() -> str:
    return os.environ["UMBOD_TEST_OTLP_BEARER_TOKEN"]


@pytest.fixture(scope="session")
def runtime_endpoints() -> RuntimeEndpoints:
    return RuntimeEndpoints(
        api_base_url=os.environ.get("UMBOD_TEST_API_BASE_URL", "http://localhost:18010"),
        otlp_base_url=os.environ.get("UMBOD_TEST_OTLP_BASE_URL", "http://localhost:14318"),
        mcp_url=os.environ.get("UMBOD_TEST_MCP_URL", "http://localhost:8011/mcp"),
        bearer_token=os.environ.get(
            "UMBOD_TEST_BEARER_TOKEN",
            "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJsb2NhbC10ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3QtdXNlckBleGFtcGxlLmNvbSIsIm5hbWUiOiJMb2NhbCBUZXN0IFVzZXIiLCJncm91cHMiOlsidGVzdCJdfQ.",
        ),
    )
