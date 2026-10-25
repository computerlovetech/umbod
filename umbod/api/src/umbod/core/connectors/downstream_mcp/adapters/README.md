# Downstream MCP adapters

- `settings.py`: application configuration translation into infrastructure settings and narrow personal identity policy.
- `identity.py`: accepted claim translation into typed personal identity facts, strict shared personal group parsing, raw machine observations and local simulated claim projection. Projection requires personal policy eligibility and authenticated single-test-user composition; it never replaces original machine observations.
- `personal_oauth/`: resumable personal provider integration, indexed in its README.
- `personal_runtime/`: owner-bound personal runtime integration, indexed in its README.

Personal ownership decisions belong to `../personal_connections/principal.py`; these adapters do not verify tokens or infer authority from caller observations.
