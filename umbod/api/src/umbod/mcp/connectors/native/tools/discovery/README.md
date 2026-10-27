# Connector discovery

`tools.py` registers gateway/code-mode search and the capability manifest transform. It captures caller authorization before asynchronous work. OpenAPI search consumes the explicitly initialized application projection in `connectors/openapi/discovery_runtime.py`, while native search consumes registry-maintained candidate snapshots.

`openapi.py` adapts normalized capabilities to candidates and deterministic lexical search. `search.py` defines the candidate/search contracts and in-memory fuzzy ranking. `manifest.py` groups accessible candidates into bounded connector-domain descriptions.
