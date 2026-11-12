import base64
import io
import json
from unittest.mock import Mock

import pytest

import setup_s3_runtime


@pytest.mark.parametrize("status", [200, 307, 412])
def test_raw_transfer_preserves_signed_target_and_binary_without_authentication(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: int,
) -> None:
    content = b"\x00\xff\x80\r\n"
    target = "/bucket/object%20name?X-Amz-Signature=private-signature&X-Amz-Credential=private-credential%2Fscope"
    headers = {"Content-Type": "application/octet-stream", "If-None-Match": "*"}
    connection = Mock(spec=["putrequest", "putheader", "endheaders", "getresponse", "close"])
    response = connection.getresponse.return_value
    response.status = status
    response.read.return_value = b"<Error><Code>PreconditionFailed</Code><Message>private-body</Message></Error>" if status == 412 else b""
    response.getheader.side_effect = ['"opaque-etag"', "0"]
    factory = Mock(return_value=connection)
    monkeypatch.setattr(setup_s3_runtime.http.client, "HTTPConnection", factory)
    monkeypatch.setattr(setup_s3_runtime.sys, "stdin", io.StringIO(json.dumps({
        "url": "http://umbod-runtime-s3:5000" + target, "method": "PUT", "headers": headers,
        "content_base64": base64.b64encode(content).decode("ascii"),
    })))
    setup_s3_runtime.transfer()
    factory.assert_called_once_with("umbod-runtime-s3", 5000, timeout=60)
    connection.putrequest.assert_called_once_with("PUT", target, skip_accept_encoding=True, skip_host=False)
    assert connection.putheader.call_args_list == [
        (("Content-Type", "application/octet-stream"),), (("If-None-Match", "*"),),
        (("Content-Length", "5"),),
    ]
    connection.endheaders.assert_called_once_with(content)
    connection.getresponse.assert_called_once_with()
    connection.close.assert_called_once_with()
    output = capsys.readouterr()
    evidence = json.loads(output.out)
    assert evidence["status"] == status
    assert evidence["code"] == ("PreconditionFailed" if status == 412 else "")
    assert evidence["request"] == {
        "original_url": True, "authorization": False, "cookie": False, "headers_preserved": True,
    }
    assert "private" not in output.out
    assert output.err == ""


def test_raw_get_preserves_complete_content_beyond_error_body_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    content = bytes(range(256)) * 32
    connection = Mock(spec=["putrequest", "putheader", "endheaders", "getresponse", "close"])
    response = connection.getresponse.return_value
    response.status = 200
    response.read.side_effect = io.BytesIO(content).read
    headers = {
        "ETag": '"tag"', "Content-Length": str(len(content)), "Content-Type": "application/octet-stream",
        "Content-Disposition": "attachment", "Cache-Control": "no-store",
    }
    response.getheader.side_effect = headers.get
    monkeypatch.setattr(setup_s3_runtime.http.client, "HTTPConnection", Mock(return_value=connection))
    monkeypatch.setattr(setup_s3_runtime.sys, "stdin", io.StringIO(json.dumps({
        "url": "http://umbod-runtime-s3:5000/bucket/object?X-Amz-Signature=secret",
        "method": "GET", "headers": {}, "content_base64": "",
    })))
    setup_s3_runtime.transfer()
    output = capsys.readouterr()
    evidence = json.loads(output.out)
    assert evidence["status"] == 200
    assert evidence["headers"] == headers
    assert base64.b64decode(evidence["content_base64"], validate=True) == content
    assert "secret" not in output.out
    assert output.err == ""
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("forbidden_header", ["Authorization", "Cookie"])
def test_raw_transfer_rejects_credentials_without_leaking_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], forbidden_header: str,
) -> None:
    connection = Mock()
    monkeypatch.setattr(setup_s3_runtime.http.client, "HTTPConnection", Mock(return_value=connection))
    monkeypatch.setattr(setup_s3_runtime.sys, "stdin", io.StringIO(json.dumps({
        "url": "http://umbod-runtime-s3:5000/bucket?X-Amz-Signature=private-signature",
        "method": "PUT", "headers": {forbidden_header: "private-credential"}, "content_base64": "",
    })))
    setup_s3_runtime.transfer()
    connection.putrequest.assert_not_called()
    connection.close.assert_called_once_with()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"error": "S3 transfer failed"}
    assert output.err == ""
