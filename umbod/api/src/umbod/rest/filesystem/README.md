# Filesystem REST boundary

Always mounted under authenticated `/api/me/filesystem`, independently of personal connections.

- `routes.py` delegates root, node and child browsing and empty file/directory creation to core ports, and includes the planned router once. File creation selects verified JSON compatibility input or rejects multipart before body parsing.
- `models.py` defines required name/metadata creation bodies and the child-list envelope. Responses use safe core `NodeSummary` projections.
- `deps.py` captures one cached request-local caller snapshot from accepted authentication state and the configured permission-group claim. Request-local services receive prepared persistence and the strict core verified identity resolver. Only configured local/dev development simulation selects LocalDevelopmentIdentityResolver with the backend subject and issuer `urn:umbod:local`. No token claims establish local authority and no administrator bypass or implicit grants exist; root access still requires an explicit issuer-qualified group grant. Private creation ownership belongs to the resolved configured USER. MCP remains strict.
- `errors.py` translates domain failures to fixed public errors without exposing exception text.
- [`planned/`](planned/README.md) indexes authenticated design-only owned/shared listing, breadcrumbs, content, rename/move/deletion and access contracts. Placeholders return sanitized no-store 501 without item lookup or writes; the same index records planned multipart upload and design-deprecated JSON empty creation.

GET routes are `/root`, `/nodes/{node_id}`, and `/nodes/{parent_id}/children`. POST `/nodes/{parent_id}/files` and `/nodes/{parent_id}/directories` return 201. Identifiers are UUIDs; creation accepts no ownership, grants, caller or content fields. Transport metadata rejects extra fields while arbitrary string attributes remain data. Root provisioning belongs to trusted setup, never requests. Existing user authentication, no-store responses and cookie mutation safeguards apply.
