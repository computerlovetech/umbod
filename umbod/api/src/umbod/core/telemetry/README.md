# Telemetry

**Module responsibility:** Validated telemetry export batches and the synchronous sink port shared by delivery boundaries.

## Entry modules

- `__init__.py` exposes `TelemetrySignal`, `TelemetryExport`, `TelemetrySink`, and `TelemetryUnavailable`.
- `models.py` defines immutable export batches with preserved JSON payloads and validated item counts.
- `ports.py` defines export delivery and unavailable-sink behavior.

## Adapters

- `adapters/in_memory.py` captures nonempty batches with explicit availability for contract testing.
- `adapters/stdout.py` emits nonempty batches through the existing structured INFO logger and its checked stdout write boundary. Disabled INFO logging, handler filtering, and observable write failures report sink unavailability. It does not configure logging.
