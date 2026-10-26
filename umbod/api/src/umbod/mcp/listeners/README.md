# MCP listeners

App composition calls `create_mcp_signals` once, or constructs channels and calls `register_mcp_listeners` exactly once. Receiver names are checked before any subscription is added, so conflicting or repeated registration is rejected without installing partial effects. Register during application composition before traffic; there are no global subscriptions.

- `registration.py`: single explicit registration point and app-scoped factory.
- `invocation_logging.py`: completion sink receiver.
- `invocation_metrics.py`: request/connector metric conversion and independently guarded inventory initialization.
- `invocation_audit.py`: completion audit receiver; protocol middleware retains ownership of request-scoped search_tools, execute_tool and execute_code.
- `failure.py`: safe signal failure reporting.

No receivers are registered at import time.
