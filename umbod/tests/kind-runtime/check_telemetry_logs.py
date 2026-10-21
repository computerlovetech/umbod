import json
import os
import sys

from check_secret_logs import check_secret_logs


_EXPECTED_SIGNALS = {"logs": "resourceLogs", "metrics": "resourceMetrics", "traces": "resourceSpans"}


def main() -> None:
    output = sys.stdin.read()
    check_secret_logs(output)
    token = os.environ["UMBOD_TEST_OTLP_BEARER_TOKEN"]
    if token in output:
        raise SystemExit("Telemetry credentials appeared in API stdout")
    if os.environ["UMBOD_TEST_ROOT_SECRET"] in output:
        raise SystemExit("Encryption credentials appeared in API stdout")
    callback_sentinels = (
        "runtime-code-must-not-be-reflected",
        "runtime-state-must-not-be-logged",
        "runtime-issuer-must-not-be-logged",
        "runtime-client-secret-must-not-be-reflected",
        "runtime-rotated-client-secret-must-not-be-reflected",
    )
    if any(sentinel in output for sentinel in callback_sentinels):
        raise SystemExit("Personal OAuth callback parameters appeared in API stdout")
    observed_signals: set[str] = set()
    for line in output.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        attributes = record.get("attributes", {})
        if attributes.get("event.name") != "umbod.telemetry.export":
            continue
        signal = attributes.get("telemetry.signal")
        if signal not in _EXPECTED_SIGNALS:
            continue
        payload = attributes.get("telemetry.payload", {})
        for resource in payload.get(_EXPECTED_SIGNALS[signal], []):
            for attribute in resource.get("resource", {}).get("attributes", []):
                if attribute.get("key") == "test.marker" and attribute.get("value", {}).get("stringValue") == f"umbod-otlp-runtime-{signal}":
                    observed_signals.add(signal)
    if observed_signals != set(_EXPECTED_SIGNALS):
        raise SystemExit("Expected authenticated OTLP exports were missing from API stdout")


if __name__ == "__main__":
    main()
