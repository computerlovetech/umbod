# Personal tools

- `models.py`: legacy administrator policy metadata, validated version-2 complete private inventories, explicit missing/present inventory revisions, public records and typed invocation/admission commands.
- `ports.py`: contract/access storage and tools-only runtime interfaces. Captured caller values and the deferred MCP caller port live in `../personal_connections/caller.py`.
- `schema_validation.py` and `contract_validation.py`: bounded offline local-reference validation, live-session safety fingerprints and private input/output validation.
- `service.py`: explicit owner discovery captures the private inventory revision before provider I/O and saves the complete encrypted inventory through compare-and-swap without publication, global catalogue writes or invocation. Legacy match-only observations require explicit rediscovery; failed and cancelled discovery preserve the previous inventory.
- `runtime.py`: disabled runtime and admitted execution from a captured personal caller value only. Listing rereads current owner availability without network access. The MCP boundary captures current callers after invocation approval and constructs operation-local services. Execution admits the captured inventory revision/fingerprint, validates input, calls the dedicated transport once and validates structured output. Missing structured output is rejected when the discovered output schema requires it.

Personal tool eligibility depends on current published server approval, verified connector-group membership, owner enablement, valid owner OAuth and the eligible private inventory. Administrator per-tool policy, activation and tool grants do not authorize or restrict personal execution. Policy edits retain private inventories. Shared and native policy remain independent.

Execution carries immutable bounded diagnostics from `core/invocation/diagnostics.py` on personal runtime exceptions before generic redaction. Context, admission, input, output and typed transport failures retain safe stage/reason codes without exception text or payloads. The MCP boundary uses invocation-local context to enrich the existing completion log only; diagnostics never enter client content or metadata.

Execution and explicit discovery catch only the transport's typed personal authorization rejection after admission/resolution, persist against the captured owner key and connection revision through their existing storage ports, and return generic unavailable failures. Generic transport failures, 403 and tool error content do not mark authorization. Failed marker persistence remains fail-closed with a sanitized operational error.

The runtime never reads shared credentials, refreshes tokens, starts consent, retries calls or caches principals/results. Authorization withdrawn before admission prevents a new downstream operation. An already admitted operation may finish within its transport deadline; revocation does not cancel already-sent work.

`personal_connections/runtime_models.py` validates optional result `_meta` as a JSON object, preserving absent and empty metadata. Successful result metadata crosses the MCP boundary only after existing error, token-reflection and output validation; it is not authorization identity. Transport request metadata restrictions do not forbid result metadata.

The MCP boundary owns approval/telemetry and public component materialization; the transport owns operation-scoped preflight/session/protocol enforcement. Resources, prompts and templates remain shared-only.
