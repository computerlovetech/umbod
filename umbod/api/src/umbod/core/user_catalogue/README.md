# User catalogue

Read-only, safe connector and capability projections for authenticated users, independent of connector-kind implementations.

- `models.py`: strict response models, including opaque session identity.
- `ports.py`: catalogue source and reader contracts.
- `in_memory.py`: in-memory source implementing the same contract.
- `service.py`: request-scoped composition and deterministic connector ordering.
- `shared.py`: publication, activation, readiness and explicit capability-grant filtering with effective descriptions.

Kind adapters and REST dependency providers compose these contracts. Shared entries require an available capability; eligible personal entries may have no tools.
