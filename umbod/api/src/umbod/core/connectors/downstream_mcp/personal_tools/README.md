# Personal tools

- `models.py`: approved contracts, private observations, owner context, public records and typed invocation/admission commands.
- `ports.py`: contract/access storage, current request context and tools-only runtime interfaces.
- `schema_validation.py` and `contract_validation.py`: bounded offline local-reference validation, contract fingerprints and approved input/output validation.
- `service.py`: explicit owner discovery and encrypted exact-match observations without publication or invocation.
- `runtime.py`: disabled runtime and admitted execution. Listing rereads current owner availability without network access. Execution resolves current context after invocation approval, admits the captured contract revision/fingerprint, validates input, calls the dedicated transport once and validates structured output. Missing structured output is rejected when an approved output schema requires it.

Execution and explicit discovery catch only the transport's typed personal authorization rejection after admission/resolution, persist against the captured owner key and connection revision through their existing storage ports, and return generic unavailable failures. Generic transport failures, 403 and tool error content do not mark authorization. Failed marker persistence remains fail-closed with a sanitized operational error.

The runtime never reads shared credentials, refreshes tokens, starts consent, retries calls or caches principals/results. Authorization withdrawn before admission prevents a new downstream operation. An already admitted operation may finish within its transport deadline; revocation does not cancel already-sent work.

The MCP boundary owns approval/telemetry and public component materialization; the transport owns operation-scoped preflight/session/protocol enforcement. Resources, prompts and templates remain shared-only.
