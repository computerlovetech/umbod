import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base: str, path: str, token: str, payload: bytes, post: bool) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    outgoing = Request(base + path, data=payload if post else None, headers=headers)
    try:
        with urlopen(outgoing, timeout=10) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def main() -> None:
    public_base, collector_base = sys.argv[1:]
    assert request(public_base, "/system/health", "", b"", False)[0] == 200
    for prefix in ("/v1/", "/api/v1/"):
        for signal in ("logs", "metrics", "traces"):
            assert request(public_base, prefix + signal, "", b"{}", True)[0] == 404
    if collector_base == "disabled":
        return
    token = os.environ["UMBOD_OTLP_BEARER_TOKEN"]
    for path in ("/health", "/ready"):
        assert request(collector_base, path, "", b"", False)[0] == 200
    for path in ("/api/admin/telemetry/log-counts", "/system/health", "/mcp"):
        assert request(collector_base, path, token, b"{}", True)[0] == 404
    for signal in ("logs", "metrics", "traces"):
        assert request(collector_base, "/v1/" + signal, "", b"{}", True)[0] == 401
        assert request(collector_base, "/v1/" + signal, token, b"{}", True)[0] == 200
    source = "helm-cohost-" + uuid4().hex
    payload = json.dumps({"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": source}}]}, "scopeLogs": [{"logRecords": [{"timeUnixNano": "1767226200000000000", "body": {"stringValue": "shared analytics check"}}]}]}]}).encode()
    assert request(collector_base, "/v1/logs", token, payload, True)[0] == 200
    query = json.dumps({"time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}, "filters": [{"dimension": "source", "values": [source]}], "group_by": [], "bucketing": {"kind": "none"}, "pagination": {"limit": 10, "offset": 0}}).encode()
    status, body = request(public_base, "/api/admin/telemetry/log-counts", os.environ["UMBOD_MCP_TEST_BEARER_TOKEN"], query, True)
    assert status == 200, (status, body)
    assert json.loads(body) == {"rows": [{"groups": [], "count": 1, "bucket": {"kind": "none"}}], "has_more": False}


if __name__ == "__main__":
    main()
