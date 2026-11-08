import base64
import json
import os
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx


def s3_runtime() -> bool:
    return os.environ.get("UMBOD_TEST_CONTENT_BACKEND") == "s3"


def assert_s3_transfer(transfer: dict[str, Any]) -> None:
    assert transfer["type"] == "single"
    assert transfer["method"] == "PUT"
    if "authorization" in transfer:
        assert transfer["authorization"] == {"type": "none"}
    parsed = urlsplit(transfer["url"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "umbod-runtime-s3:5000"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Signature"]
    headers = {name.lower(): value for name, value in transfer["headers"].items()}
    assert not {"authorization", "cookie", "x-umbod-upload-token"} & headers.keys()
    assert headers["if-none-match"] == "*"
    assert headers["content-type"]
    assert "content-length" not in headers
    assert {"host", "content-type", "content-length", "if-none-match"} <= set(query["X-Amz-SignedHeaders"][0].split(";"))


def raw_s3_request(transfer: dict[str, Any], content: bytes, method: str = "PUT") -> httpx.Response:
    payload = json.dumps({"url": transfer["url"], "headers": transfer["headers"], "method": method,
                          "content_base64": base64.b64encode(content).decode("ascii")})
    try:
        result = subprocess.run([
            "kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"],
            "exec", "-i", "deployment/umbod-core", "-c", "api", "--", "python",
            "/s3-fixture/setup_s3_runtime.py", "transfer",
        ], input=payload, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        raise AssertionError("In-cluster S3 transfer timed out") from None
    assert result.returncode == 0, "In-cluster S3 transfer process failed"
    try:
        evidence = json.loads(result.stdout)
    except ValueError:
        raise AssertionError("In-cluster S3 transfer returned invalid evidence") from None
    assert "error" not in evidence, "In-cluster S3 transfer failed"
    assert evidence["request"] == {"original_url": True, "authorization": False, "cookie": False,
                                   "headers_preserved": True}
    return httpx.Response(evidence["status"], headers=evidence["headers"], json={"code": evidence["code"]})


def transfer_upload(client: httpx.Client, transfer: dict[str, Any], content: bytes) -> httpx.Response:
    if s3_runtime():
        assert_s3_transfer(transfer)
        return raw_s3_request(transfer, content)
    return client.put(transfer["url"], headers=transfer["headers"], content=content)


def assert_transfer_succeeded(response: httpx.Response) -> None:
    assert response.status_code == (200 if s3_runtime() else 204), "Upload transfer failed"
    if s3_runtime():
        assert response.headers["etag"]
    else:
        assert response.headers["cache-control"] == "no-store"
