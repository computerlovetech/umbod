# MCP metrics

- `models.py` and `recorder.py`: neutral invocation identity/completion models and the invocation metrics port.
- `in_memory.py`: invocation recorder for interface-level tests.
- `protocol_models.py` and `protocol_recorder.py`: validated protocol request/list-size observations and recorder port, separate from tool invocation completion.
- `prometheus.py`: application-owned Prometheus registry implementing invocation and protocol recording. Protocol timing labels are bounded method/outcome values; list sizes have no identity labels.
- `http_server.py`: metrics endpoint lifecycle.
- `__init__.py`: public recorder and observation exports.

Protocol middleware times initialize and tools/list without recording credentials, private descriptors or owner identities. Runtime rebuild and synchronization failures are logged at their application-owned reconciliation boundary. Inventory initialization and invocation metric ownership remain in the neutral signal listeners.
