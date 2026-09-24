from typing import Final

APP_NAME: Final[str] = "umbod"
LOG_LEVEL: Final[str] = "info"

PUBLIC_SITE_ORIGIN: Final[str] = "http://localhost:3010"
PUBLIC_API_ORIGIN: Final[str] = "http://localhost:18010"
PUBLIC_MCP_ORIGIN: Final[str] = "http://localhost:8011"
INTERNAL_API_ORIGIN: Final[str] = ""

DATA_DIR: Final[str] = ".data"
CONNECTOR_STORE_SQLITE_PATH: Final[str] = ".data/umbod.sqlite3"
LOCAL_CONNECTOR_CONFIGURATION_SECRET: Final[str] = "umbod-local-connector-configuration-secret"
LOCAL_DOWNSTREAM_MCP_CREDENTIAL_SECRET: Final[str] = "umbod-local-downstream-mcp-secret"
OPENAPI_JSON_IMPORT_MAX_BYTES: Final[int] = 10_485_760
OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS: Final[float] = 10.0
OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS: Final[float] = 30.0
OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS: Final[float] = 10.0
OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS: Final[float] = 5.0
OAUTH_STORAGE_DIRECTORY: Final[str] = ".data/fastmcp-oauth"

REST_PORT: Final[int] = 8000
REST_METRICS_PORT: Final[int] = 8001
MCP_PORT: Final[int] = 8011
MCP_METRICS_PORT: Final[int] = 8012
MCP_TOOL_EXPOSURE_MODE: Final[str] = "flat"
MCP_CODE_EXECUTION_TIMEOUT_SECONDS: Final[float] = 30.0
MCP_MAXIMUM_UPLOADED_FILE_BYTES: Final[int] = 10 * 1024 * 1024
MCP_DOWNSTREAM_DISCOVERY_ENABLED: Final[bool] = True
MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS: Final[float] = 10.0
MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS: Final[float] = 60.0
MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY: Final[int] = 4
MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO: Final[float] = 0.1
MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS: Final[float] = 900.0
MCP_TEST_USER_EMAIL: Final[str] = "test-user@example.com"
MCP_TEST_BEARER_TOKEN: Final[str] = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJsb2NhbC10ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3QtdXNlckBleGFtcGxlLmNvbSIsIm5hbWUiOiJMb2NhbCBUZXN0IFVzZXIiLCJncm91cHMiOlsidGVzdCJdfQ."
)
MCP_TEST_USER_GROUP: Final[str] = "test-group"

PERMISSION_GROUP_CLAIM: Final[str] = "groups"
AUTH0_PERMISSION_GROUP_CLAIM: Final[str] = "permissions"

ADMIN_JWT_HEADER_NAME: Final[str] = "X-Forwarded-Access-Token"
ADMIN_REQUIRED_MEMBERSHIP: Final[str] = "umbod-admins"
ADMIN_SIMULATED_USER_ID: Final[str] = "simulated-user"
ADMIN_SIMULATED_USER_EMAIL: Final[str] = "test-user@example.com"
ADMIN_SIMULATED_USER_NAME: Final[str] = "Test User"
