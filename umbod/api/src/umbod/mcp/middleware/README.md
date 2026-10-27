# MCP middleware

- `audit.py`: request-level audit ownership and completion recording for orchestration tools.
- `protocol_metrics.py`: initialize and tools/list timing, cancellation/error outcomes, and successful list-size observations through the protocol metrics port. Recorder failures do not change protocol results. Metrics dimensions are bounded method/outcome values; private schemas, credentials, tool names and owners are not labels.
- `__init__.py`: public middleware exports.

Personal namespace and authoritative resolved-component protection remain in `connectors/downstream_mcp/personal_runtime.py`. They use the initialized application runtime rather than reading shared definitions during requests.
