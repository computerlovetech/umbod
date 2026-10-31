# Configuration

Configure Umbod through Helm values and Kubernetes Secrets. Review the [generated Helm values reference](../reference/helm-values.md) for every supported value, default, and schema constraint.

## Profiles

| Helm value | Default | Purpose |
| --- | --- | --- |
| `config.profile` | `production` | Selects local or production behavior |
| `config.authentication.mode` | `auth0` | Selects development authentication or an OIDC provider |
| `config.logLevel` | `info` | Sets application logging verbosity |

For local evaluation, set `config.profile=local` and `config.authentication.mode=dev`. Application services emit OpenTelemetry-compatible JSON logs to standard output for collection by the Kubernetes container runtime.

## Public origins

Set origins without a trailing path:

| Helm value | Purpose |
| --- | --- |
| `config.publicOrigins.site` | Browser-facing Umbod origin |
| `config.publicOrigins.api` | Browser-facing REST API origin |
| `config.publicOrigins.mcp` | Agent-facing MCP origin |

These values drive API and MCP URLs, allowed browser origins, OIDC metadata, and authentication redirects. They must match the URLs visible to users and MCP clients.

## Persistence

Umbod uses SQLite for development and evaluation. Persistence is disabled by default, so data is lost when the core Pod is replaced.

Set `persistence.enabled=true` to create a ReadWriteOnce PersistentVolumeClaim. Configure `persistence.size`, `persistence.storageClass`, and `persistence.accessModes` as required, or set `persistence.existingClaim` to use an existing ReadWriteOnce claim.

Umbod does not migrate SQLite schemas or persisted documents between incompatible versions. Reset persistent storage before installing an incompatible Umbod version.

## Filesystem runtime

The application environment contract selects local or S3 file-content storage independently of the application database backend. Local storage remains the default for operator deployments. Namespace, ownership and grants use the existing application database; content storage does not create another database runtime. Embedded hosts constructing `AppConfig` directly default to in-memory content.

| Environment variable | Default | Contract |
| --- | --- | --- |
| `UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES` | `10485760` | Positive maximum filesystem upload size in bytes; independent of the MCP connector file-input limit |
| `UMBOD_FILESYSTEM_CONTENT_BACKEND` | `local` | Content driver: `local` or `s3` |
| `UMBOD_FILESYSTEM_CONTENT_DIRECTORY` | derived | Local-only nonblank directory override; otherwise `filesystem-content` beneath `UMBOD_DATA_DIR`, whose default is `.data` |
| `UMBOD_FILESYSTEM_S3_BUCKET` | empty | Required pre-existing general-purpose bucket when selecting S3 |
| `UMBOD_FILESYSTEM_S3_REGION` | `us-east-1` | S3 signing region |
| `UMBOD_FILESYSTEM_S3_ENDPOINT_URL` | empty | AWS endpoint resolution, or an explicit credential-free HTTP(S) S3-compatible endpoint |
| `UMBOD_FILESYSTEM_S3_PREFIX` | empty | Optional relative prefix without leading/trailing slashes, empty segments, or dot segments |
| `UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE` | `auto` | `auto`, `virtual`, or `path`; compatible services may require `path` |

Directory configuration is normalized during operator-to-runtime assembly, preserving relative paths and expanding the home directory. Configuration does not create directories or inspect their contents. Retain the content directory alongside the application database to preserve file references across restarts. Workers sharing a namespace database must also share the same content directory. Instance configuration inspection exposes the upload limit but omits the host directory. These are application environment settings, not dedicated Helm values.

For S3, configure identical bucket, region, endpoint, prefix, and addressing style for API and MCP workers. Credentials use the AWS SDK provider chain; environment access keys, profiles, and workload identities are not copied into Umbod configuration. Provision the bucket, encryption policy, and permissions separately. Application credentials need `s3:GetObject`, `s3:PutObject`, and `s3:AbortMultipartUpload` on the selected object prefix; bucket encryption may require additional KMS permissions. The driver does not require bucket creation or listing. Use HTTPS outside trusted local test networks. An explicit local directory cannot be combined with S3, and nondefault S3 settings cannot be combined with local storage. Changing a populated deployment's backend, bucket, or prefix requires a separately planned content migration preserving existing logical keys; there is no automatic migration or fallback.

Supply application settings through both `core.api.env` and `core.mcp.env` in Helm, and provider credentials through the shared `existingSecret` or externally managed workload identity. Docker Compose forwards content settings and AWS access-key, secret-key, and session-token environment variables to both services. S3 does not replace the application database or its persistence requirements. See [S3 file-content storage](s3-file-storage.md) for Helm configuration, credentials, and operational boundaries.

REST uploads create an authenticated session, transfer raw bytes, and explicitly complete publication. Zero-byte uploaded files are allowed. Files remain invisible until completion and duplicate names are rejected without overwriting. New files remain private to their creator; parent grants are not inherited. S3 remains a low-level driver: transfers still pass through Umbod, without presigned URLs or client-side multipart coordination. The byte limit is not a storage quota. Content is stored before namespace publication, so failed publication can leave unreferenced immutable objects; automatic garbage collection is not implemented. Configure bucket lifecycle rules for abandoned multipart uploads because process termination or failed abort requests may leave incomplete parts.

The frontend nginx proxy limits the entire request body to 12 MiB. Increasing the API file limit requires corresponding gateway/proxy configuration. Direct API ingress does not pass through that frontend limit.

Downloads use the stable authenticated node-content endpoint and return attachments with no-store caching. Clients must tolerate a future temporary redirect to a short-lived storage URL without forwarding API credentials to another origin.

## Authentication and secrets

Shared installations require an OIDC provider and stable secrets. Configure non-secret authentication settings with the typed `config` Helm values, including:

- `config.authentication.oidc.domain`
- `config.authentication.oidc.clientId`
- `config.authentication.oidc.audience`
- `config.authentication.oidc.requiredScopes`
- `config.authorization.adminGroup`
- `config.authorization.adminMembershipClaim`
- `config.authorization.mcpPermissionClaim`

Create a Kubernetes Secret containing `UMBOD_ROOT_SECRET` and `UMBOD_OIDC_CLIENT_SECRET`, then set `existingSecret` to its name. Do not place secret values directly in a Helm values file.

!!! warning
    `UMBOD_ROOT_SECRET` is the sole derivation root for backend security secrets. Rotating it invalidates derived credentials.

### Server startup requirement

Every API and MCP server profile, including `local`/`dev`, requires a nonblank `UMBOD_ROOT_SECRET` from the environment or `.env`. Configure a persistent secret yourself; Umbod never generates one. API and MCP must use the same value, stable across restarts. Missing, empty or whitespace-only values fail startup before application composition, persistence or metrics listeners.

The supported `umbod api serve` and `umbod mcp serve` commands check this before calling Uvicorn, including before its reload parent can bind HTTP sockets. Normal ASGI factory/lifespan startup also rejects an absent or blank root. Externally prebound sockets and an external Uvicorn reload parent's socket binding are outside the application's guarantee. Default Docker Compose configuration rejects missing or empty values before services or mapped ports start; whitespace-only values are rejected by application startup.

`umbod config show` and `umbod config validate` retain configuration inspection and structural validation semantics: a secretless local configuration can still be inspected or validated. Existing production validation remains strict. Explicit embedding with a typed `AppConfig` containing derived secrets does not reload operator settings or require a root field on `AppConfig`.

## Personal connections identity policy

For administrator setup, user sign-in, discovery, and access controls, see [Shared and Personal connectors](../using-umbod/connectors.md).

| Environment variable | Default | Contract |
| --- | --- | --- |
| `UMBOD_PERSONAL_CONNECTIONS_ENABLED` | `auto` | Automatically enable authenticated personal catalogue selection when an identity namespace is supplied or derived for local/dev; `false` explicitly opts out |
| `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` | empty | Stable identity authority; local/dev automatic selection derives `test:umbod-local` only when exactly empty; otherwise explicit when enabled |
| `UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED` | `auto` | Automatically enable durable personal authorization when selection, persistent SQLite and encryption are configured; `false` explicitly opts out |

Both switches accept `auto`, `true` or `false`. No extra feature opt-in is needed on configured deployments: supplying the stable namespace enables selection, and durable SQLite plus a nonblank root secret additionally enables authorization. Ordinary `local`/`dev` startup enables personal MCP server registration by default: automatic selection with an exactly empty namespace derives the stable `test:umbod-local` authority. Set `UMBOD_PERSONAL_CONNECTIONS_ENABLED=false` to opt out. Explicit modes and supplied namespaces are never replaced; explicit `true` still requires an explicit namespace. Real providers and production never receive a fallback and require an explicit namespace to enable registration. Missing durability or encryption leaves automatic OAuth unavailable without disabling selection. This default does not generate a root secret, change OAuth/provider requirements or provide real-account sign-in under development authentication. Malformed supplied namespaces or unsafe authentication fail validation rather than silently disabling the feature. Explicit `true` still rejects missing prerequisites. Selection `false` prevents automatic OAuth; explicitly requesting OAuth with selection disabled is invalid. Inspection reports resolved booleans, not operator mode strings. Embedded hosts constructing `AppConfig` directly still supply resolved booleans explicitly. Docker Compose forwards the same modes, namespace and optional SQLite path to API and MCP services.

An enabled policy requires non-disabled REST and MCP authentication. Production requires real REST JWT verification, `UMBOD_OIDC_ISSUER_URL`, `UMBOD_OIDC_AUDIENCE`, a configured or derived `UMBOD_ADMIN_JWKS_URL`, MCP OIDC and a supported Google, Auth0 or Entra provider. An Auth0 domain may derive the upstream issuer. Development semantic JWT verification or simulation requires a namespace beginning `test:` with a nonblank suffix, derived only for the local/dev automatic case above; production rejects those modes. A development REST authentication environment selects semantic verification even when JWT mode, an OIDC recipe and complete OIDC settings are configured; the same restrictions apply to direct application composition. Direct application configuration constructors enforce the same constraints.

Choose a distinct namespace for each identity authority and preserve it across REST and MCP and restarts. The local/dev fallback is deterministic and shared by both services; retain an existing explicit namespace for ownership continuity. Changing it changes ownership; never derive it from a request issuer, email, client ID or the outer MCP proxy URL. Google and Auth0 use verified nonblank string `sub`; Entra uses the configured tenant plus verified `oid`, requires a matching `tid` and delegated `scp`, and ignores application-specific `sub`. Known machine-only identities are rejected. Present issuers must exactly match the configured upstream issuer; only Google upstream tokeninfo claims may omit `iss`. The current FastMCP access-token context supplies upstream verified claims, not the outer proxy JWT. Missing or invalid canonical identities cannot access personal state. Do not enable personal writes while older workers remain active. Personal authorization is available automatically when its prerequisites are met and requires a persistent, non-memory SQLite path shared by all API workers with the same nonblank root secret and SQLite-compatible locking/storage semantics. Separate pod-local databases are unsupported. In-memory storage remains useful for port contracts, not exposed authorization. SQLite retains its development/evaluation deployment limitations. The callback base is derived only from `UMBOD_PUBLIC_API_ORIGIN` and `/api/oauth/downstream-mcp/callback`, not forwarded headers. Providers advertising issuer-bearing callbacks use this generic route; otherwise Umbod binds the redirect to `/api/oauth/downstream-mcp/callback/issuer/<digest>`, where the digest is the lowercase SHA-256 hex digest of the exact discovered issuer. Preconfigured provider applications must register the exact selected redirect URI. Expose both callback route forms. Expose the callback without gateway authentication and redact its query at ingress/reverse-proxy/tracing/error-reporting boundaries: application redaction cannot protect earlier logs. Provider support requires protected-resource/issuer metadata and S256 PKCE. Generic callbacks require a matching issuer parameter; issuer-specific callbacks may omit it only when the route matches the saved issuer binding. Production callbacks require HTTPS; trusted local/dev simulation may use validated HTTP loopback callbacks. Administrator policy supplies requested scopes and either public dynamic registration or a preconfigured public/confidential client pinned to its issuer. Confidential methods are explicit Basic or POST; there is no registration or authentication fallback. Scoped grants may narrow but never exceed the requested set. See the [provider-policy contract](personal-downstream-mcp-provider-policy-specification.md). Suppress or redact secret-bearing administrator request bodies and Authorization headers in proxies, tracing and error reporting as well. See the [authorization specification](personal-downstream-mcp-authorization-specification.md). Administrator publication and connector-level group grants, explicit per-user enablement, downstream sign-in, and a valid private tool inventory remain mandatory; automatic feature availability never connects accounts or grants consent. After completed browser sign-in, the UI attempts initial private tool discovery automatically; users can explicitly refresh tools or retry loading after a failure. Eligible users can execute tools from their private inventory. Personal connector grants cover all tools exposed to that downstream user, including tools added after explicit rediscovery; administrator per-tool approval and activation are not personal execution prerequisites.

## Optional user-profile enrichment

The application environment contract supports optional enrichment of `/api/admin/users`; the Helm chart has no dedicated profile values. Access tokens remain the sole authentication and membership authority. The response keeps `id`, `email`, `name`, and `picture`; `id` always comes from the verified access subject.

| Environment variable | Default | Contract |
| --- | --- | --- |
| `UMBOD_USER_PROFILE_MODE` | `access_claims` | `access_claims` or `id_token` |
| `UMBOD_USER_PROFILE_JWT_HEADER` | `X-Auth-Request-ID-Token` | Dedicated ID-token header, never Authorization or the configured access header |
| `UMBOD_USER_PROFILE_NAME_CLAIM` | `name` | Exact literal display-name claim key |
| `UMBOD_USER_PROFILE_EMAIL_CLAIM` | `email` | Exact literal email claim key |
| `UMBOD_USER_PROFILE_PICTURE_CLAIM` | `picture` | Exact literal picture claim key |

Mappings apply to the selected profile source and support namespaced keys without dot traversal. Blank mappings and invalid or conflicting header names fail startup. ID-token mode requires real production JWT authentication, a configured OIDC issuer, admin JWKS URL, and OIDC client ID. It is rejected with development semantic verification, simulation, or disabled authentication.

ID tokens require RS256, exact issuer, client-ID audience (not the API audience), and `iss`, `aud`, `exp`, and `sub`. Multiple audiences require `azp` matching the client ID; any present `azp` must match. Verified ID issuer and subject must match verified access issuer and subject. The dedicated header has no Authorization fallback and expects the raw ID token.

Missing profile headers preserve access-only clients. Present invalid, expired, incorrectly addressed, or identity-mismatched profile tokens are ignored in full; a structured warning records only a rejection category, and verified access claims provide the fallback. Profile failures never cause their own 401 or grant permissions. Valid ID tokens with unavailable fields return `unknown` name and nullable email/picture rather than mixing sources. No UserInfo network lookup is performed. Profile verification shares a root-lifespan JWKS cache through Starlette's yielded lifespan state mapping and request-state dependencies, with single-flight locking, a five-minute TTL, five-second unknown-key/failure refresh cooldown, and a three-second fetch timeout. A new key ID can trigger an early refresh; concurrent requests reuse its result. `/users` executes synchronous profile lookups in FastAPI's threadpool so key-fetch delays do not block unrelated event-loop requests. Authentication debug mode logs only credential-presence booleans, including configured access/profile headers, not tokens, header values, identity fields, or decoded JWT contents.

Gateways must overwrite client-supplied credential headers and prevent profile token exposure in browser responses. Compose exports ID tokens separately while keeping Authorization and the access header bound to access tokens; its default mode stays `access_claims` so development authentication continues to work.

## Images

The chart selects the released core and frontend images through `core.image` and `frontend.image`. Use the image tags shipped with the chart release. Do not use floating tags.

## Connector plugins

Configure a plugin-bundle image with `plugins.image` and allow its connector IDs with `plugins.availableConnectorIds`. See [Connector plugins](../plugins/index.md) for the lifecycle and security model.

## Source of truth

The published chart values and the [generated Helm values reference](../reference/helm-values.md) are the source of truth for supported operator configuration.
