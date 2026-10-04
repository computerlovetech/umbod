# Telemetry receiver

**Module responsibility:** OTLP/HTTP JSON ingestion for logs, metrics, and traces.

## Modules

- `composition.py` installs root signal routes, configuration dependency overrides, and OTLP error responses.
- `dependencies.py` authenticates dedicated bearer credentials and supplies request-scoped sinks using acknowledged writes through the existing stdout logger.
- `routes.py` coordinates media-type checks, bounded reads, schema validation, and sink invocation.
- `body.py` streams bounded uncompressed and gzip bodies.
- `validation.py` validates canonical OTLP requests with JSON-specific identifiers and enums.
- `errors.py` defines safe HTTP failures.

Core contracts and sink adapters live in `umbod.core.telemetry`. Operator behavior and deployment paths are described in `umbod/docs/reference/telemetry-ingestion.md`.
