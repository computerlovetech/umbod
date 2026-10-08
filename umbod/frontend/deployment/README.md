# Static frontend deployment

**Module responsibility:** Non-root nginx runtime, SPA routing, public browser configuration, and optional local API forwarding. Bun builds the static adapter output; Node and application dependencies are absent from the runtime image.

## Entrypoints

- `start.sh` generates configuration atomically and starts nginx.
- `generate-config.sh` serializes only `PUBLIC_API_BASE_URL` and `PUBLIC_MCP_BASE_URL` through jq as the `apiBaseUrl` and `mcpBaseUrl` JSON fields. Defaults are `/api` and `/mcp`. No other environment value enters the payload.
- `nginx.conf` uses writable temporary paths and port 3000.
- `default.conf.template` serves `/app-config.json`, independent `/system/health`, immutable assets, and the `200.html` SPA fallback. Missing `/_app/` assets return 404. HTML and public configuration use `Cache-Control: no-store`.

`API_PROXY_ORIGIN` is a server-only local routing setting, not browser configuration. Compose and Helm set it to the Python API Service so local frontend port-forwards remain functional; nginx retains `/api/` and forwards Authorization, Cookie, Origin, and forwarded host/protocol headers. DNS resolution uses the container's resolver configuration in Docker and Kubernetes. Production ingress routes `/api` directly to Python without stripping the prefix. API requests must never fall through to the SPA shell or map to internal `/system` endpoints.

Only Python validates administrator credentials and permissions. For the Compose authenticated admin host, the higher-priority API router uses oauth2-proxy `/oauth2/auth` without the HTML sign-in error middleware. Web page routes retain that middleware and login flow. The directly exposed API origin still requires backend authentication in production. Compose defaults `UMBOD_ADMIN_JWT_HEADER` to `X-Auth-Request-Access-Token`; native requests without that header fall back to `Authorization`. Configure the gateway login to request a JWT access token for `UMBOD_OIDC_AUDIENCE` and include the administrator membership claim. oauth2-proxy's `--set-authorization-header` forwards an ID token, which is not a substitute for an audience-selected API access token. External provider login and production session renewal require verification with the deployment's identity provider.
