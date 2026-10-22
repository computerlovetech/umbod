# Hosting

Backend composition API for the separate Umbod REST and MCP services and explicit application embedding. The retired Desktop product is no longer a supported host.

## Supported API

Import composition functions and contracts from `umbod.hosting`. Synchronous `create_rest_app` returns FastAPI; asynchronous `create_mcp_app` returns Starlette. Both require explicit `AppConfig`. Importing the package does not load environment configuration or construct applications.

Supported contract reexports are `AppConfig`, `ConnectorRegistration`, `JwtVerifier`, `JwtClaims`, `JwtVerificationError`, `OAuthService`, `MCPAuthProvider`, `InMemoryGroupConnectorToolPermissions`, `McpToolInvocationLogSink`, `McpToolInvocationLogEvent`, `AccessToken`, and `TokenVerifier`. They retain the underlying types' identity; annotations do not check protocol conformance at runtime.

REST requires explicit connector-registration, administrator-verifier and shared-OAuth-service hook selection. Existing hooks accept None for configured/default selection. An empty registration sequence remains an explicit override. The new optional `user_verifier` keyword independently selects authentication for `/api/me`; its omitted/None value uses configured verification and never inherits `admin_verifier`. Existing callers remain compatible. An explicit keyword resolver accepts this optional hook and rejects unknown keywords without introducing parameter defaults. Personal selection routes require a validated canonical identity policy; operator configuration enables availability automatically when its namespace is supplied, with an explicit opt-out. Durable personal authorization defaults available when selection, shared persistent SQLite and a nonblank encryption secret are configured, unless explicitly opted out; it uses its own request-scoped provider and does not inherit the shared `OAuthService` hook. The state-bound callback is public at the API boundary; hosting gateways must exempt that exact route from authentication and redact query secrets before logging. Supplied verifiers are trusted deployment infrastructure and must validate tokens before returning claims.

MCP requires explicit auth-provider, group-permission runtime-state and completed-invocation-sink hook selection. None retains configured authentication and logging; it does not disable them. Internal `PublicAppConfig` and runtime contexts are not hosting contracts.

## Ownership and lifecycle

`applications.py` assembles backend applications; `contracts.py` owns supported reexports. App lifespans own persistence, metrics listeners, MCP workers and synchronization tasks. A deployment supplying an `OAuthService` owns its shutdown. Embedding callers must enter returned ASGI lifespans. Personal application services, repositories and principal providers are request-scoped; no caller identity is retained on shared application state.

MCP composition closes acquired persistence on configuration acquisition or later construction failure, including cancellation. Successful composition leaves shutdown to its lifespan. REST delegates to its legacy factory: construction failures before lifespan startup are not covered by lifespan shutdown. This API does not claim construction rollback for REST.

## Service entrypoints

`rest_service.py` is the zero-argument Uvicorn factory: it loads configuration, configures logging and constructs REST. `mcp_service.py` exports an import-safe Starlette shell; its lifespan loads configuration, composes MCP in the active event loop and enters the returned application's lifespan. HTTP forwarding is mounted only while that lifespan is active. Construction/startup failures propagate through ASGI startup. Both environment-backed entrypoints require a nonblank `UMBOD_ROOT_SECRET` before composition, persistence or metrics. Explicit typed embedding remains independent of operator secrets. The supported Umbod CLI also preflights before Uvicorn reload-parent binding; external reload-parent or prebound sockets are outside the application guarantee.

CLI services remain separate processes; Kubernetes chart wiring is unchanged. Legacy REST invocation forms remain supported, now with an independent optional `user_verifier` keyword. Legacy MCP factories delegate to hosting composition.

Explicit settings avoid operator environment loading, but native connector deployment declarations still come from `UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH`. Synchronization may use system HTTP endpoints or SQL events. Hosting boundary and service tests cover import safety, signature compatibility, verifier isolation, lifecycle ownership and forwarding.
