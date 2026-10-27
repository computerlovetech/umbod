# User catalogue

Read-only, safe connector and capability projections for authenticated users, independent of connector-kind implementations.

- `models.py`: strict response models, including opaque session identity. `CatalogueToolCapability` requires the permitted tool's `input_schema` JSON object and explicit `output_schema` absent/present state; `CatalogueCapability` covers prompts, resources and resource templates without schema fields. Connector capabilities use a kind-discriminated union. `key` remains the identifier and `name` the display title.
- `ports.py`: catalogue source and reader contracts.
- `read_state.py`: request-local publication, activation and caller-group permission snapshots registered with a caller-owned read plan; resolution performs no I/O. Each context deduplicates IDs and uses batches of at most 200 IDs, with no reads for empty inputs.
- `in_memory.py`: in-memory source implementing the same contract.
- `service.py`: request-scoped composition and deterministic connector ordering.
- `readiness.py`: request-local reuse of connector-invariant native configuration readiness; capability-dependent readiness must not use this adapter.
- `shared.py`: publication, activation, readiness and explicit capability-grant filtering with effective descriptions and normalized tool schema projection after availability checks.

Kind adapters and REST dependency providers compose these contracts. Shared entries require an available capability; eligible personal entries may have no tools.
