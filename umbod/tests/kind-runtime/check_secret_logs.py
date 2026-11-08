import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote


S3_CREDENTIAL_MARKER = re.compile(r"x-amz-(?:signature|credential|security-token)", re.IGNORECASE)


def decoded_log_line(line: str) -> str:
    for _ in range(8):
        decoded = unquote(line)
        if decoded == line:
            break
        line = decoded
    return line


def sensitive_values() -> list[str]:
    values = [os.environ[key] for key in ("UMBOD_TEST_OTLP_BEARER_TOKEN", "UMBOD_TEST_ROOT_SECRET", "UMBOD_TEST_BEARER_TOKEN", "UMBOD_TEST_BEARER_TOKEN_B", "UMBOD_TEST_AWS_ACCESS_KEY_ID", "UMBOD_TEST_AWS_SECRET_ACCESS_KEY") if os.environ.get(key)]
    proxy_tokens = os.environ.get("UMBOD_TEST_PERSONAL_PROXY_TOKENS", "")
    if proxy_tokens and Path(proxy_tokens).exists():
        values.extend(Path(proxy_tokens).read_text().splitlines())
    values.extend(("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "kind-disposable-identity-client-secret", "kind-personal-downstream-token-", "kind-personal-refresh-token-", "runtime-code-must-not-be-reflected", "runtime-state-must-not-be-logged", "runtime-issuer-must-not-be-logged", "runtime-client-secret-must-not-be-reflected", "runtime-rotated-client-secret-must-not-be-reflected"))
    return values


def check_secret_logs(output: str) -> None:
    if (
        any(value in output for value in sensitive_values())
        or re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*", output)
        or S3_CREDENTIAL_MARKER.search(decoded_log_line(output))
    ):
        raise SystemExit("Sensitive credentials or OAuth parameters appeared in service stdout")


def redacted_diagnostics(output: str) -> str:
    output = "".join(
        "[REDACTED S3 SIGNED REQUEST]\n" if S3_CREDENTIAL_MARKER.search(decoded_log_line(line)) else line
        for line in output.splitlines(keepends=True)
    )
    redacted = re.sub(r"-----BEGIN (?:RSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA )?PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", output)
    redacted = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*", "[REDACTED JWT]", redacted)
    redacted = re.sub(r"kind-personal-(?:downstream|refresh)-token-[A-Za-z0-9_-]+", "[REDACTED TOKEN]", redacted)
    redacted = re.sub(r"([?&](?:code|state)=)[^&\s\"\\]+", r"\1[REDACTED]", redacted)
    for value in sensitive_values():
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


if __name__ == "__main__":
    output = sys.stdin.read()
    if sys.argv[1:] == ["--diagnostics"]:
        sys.stdout.write(redacted_diagnostics(output))
    check_secret_logs(output)
