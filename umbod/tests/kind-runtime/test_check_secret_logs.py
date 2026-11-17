from urllib.parse import quote

import pytest

from check_secret_logs import check_secret_logs, redacted_diagnostics


@pytest.mark.parametrize("marker", ["X-Amz-Signature", "X-Amz-Credential", "X-Amz-Security-Token"])
@pytest.mark.parametrize("encoding", ["plain", "percent", "double-percent"])
def test_signed_s3_credentials_are_detected_and_redacted(marker: str, encoding: str) -> None:
    secret = "private-runtime-signed-value"
    line = "http://s3.invalid/object?" + marker + "=" + secret + "&other=value"
    if encoding != "plain":
        line = "".join(f"%{byte:02x}" for byte in line.encode())
    if encoding == "double-percent":
        line = quote(line, safe="")
    output = "safe before\n" + line + "\nsafe after\n"
    with pytest.raises(SystemExit, match="Sensitive credentials"):
        check_secret_logs(output)
    redacted = redacted_diagnostics(output)
    assert redacted == "safe before\n[REDACTED S3 SIGNED REQUEST]\nsafe after\n"
    assert secret not in redacted
    check_secret_logs(redacted)


def test_dynamic_registration_secrets_are_detected_and_fully_redacted() -> None:
    secret = "kind-personal-dcr-secret-unique-confidential-value"
    output = "OAuth diagnostic " + secret + "\n"
    with pytest.raises(SystemExit, match="Sensitive credentials"):
        check_secret_logs(output)
    redacted = redacted_diagnostics(output)
    assert redacted == "OAuth diagnostic [REDACTED CLIENT SECRET]\n"
    assert "unique-confidential-value" not in redacted
    check_secret_logs(redacted)


def test_ordinary_s3_diagnostics_are_preserved() -> None:
    output = "S3 upload completion rejected: checksum mismatch\n"
    check_secret_logs(output)
    assert redacted_diagnostics(output) == output
