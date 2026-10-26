# Kind runtime verification

`run.sh` builds application images and runs serial service checks in a disposable Kind cluster. Existing clusters are rejected rather than reused or deleted. Cluster name and forwarded ports can be isolated with the runner's `UMBOD_TEST_*` environment variables.

## Phases

- The initial local-test authentication phase runs general runtime checks, `test_running_groups.py`, and `test_running_filesystem_unverified.py`. Shared-group checks verify idempotent registration, catalogue reuse by connector permissions, no implicit filesystem grants, usage-protected deletion through both APIs, and retention after removing filesystem access. Tokenless REST requests use the configured Test User. Filesystem access still requires explicit root grants: the test configures the local authority through the admin API, creates a private folder and revokes the grants. MCP continues to reject its local test identity.
- `setup_personal_runtime.py` installs a disposable TLS identity provider, signed JWT/JWKS authentication and additional API/MCP workers. It does not bootstrap filesystem ownership or grants.
- The verified phase runs personal execution checks and `test_running_filesystem.py`. The filesystem test configures signed-user group access through the authenticated admin API, then checks REST/MCP and workers, authentication-derived group access, private creator ownership, authority-injection rejection, live root-group revocation and stale-editor protection. Planned browser operations and multipart uploads return authenticated, no-store `501` responses without changing root policy.
- Log checks run before cleanup. Failure diagnostics are emitted by the runner; its owned cluster and temporary secrets are removed unless explicit keep-cluster configuration is selected.

The connector, identity fixture, test-only values, bootstrap grant and extra worker deployment remain under this directory or runtime test code. They do not enter the published chart or application images. Ordinary user filesystem requests and application startup never provision filesystem ownership or grants. Explicit authenticated admin policy saves can initialize and update the system-owned root.
