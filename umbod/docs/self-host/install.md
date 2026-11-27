---
description: Install Umbod on a shared Kubernetes cluster with OIDC sign-in, HTTPS, and persistent storage.
---

# Install for a team

Install Umbod on a Kubernetes cluster with your identity provider, HTTPS, and persistent storage. To try it first, [run it locally](local.md).

!!! warning "Early beta"
    The chart runs one replica on SQLite. Persistent storage keeps your data, but Umbod is not highly available.

## Before you start

| You need | Notes |
| --- | --- |
| Kubernetes 1.25 or newer | With an ingress controller and a storage class |
| Helm 3, `kubectl`, OpenSSL | On your machine |
| A hostname with TLS | For example `umbod.example.com` |
| An OIDC provider | Auth0, Microsoft Entra, or Google. Access tokens must carry a groups claim |
| A sign-in gateway | For example [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/). The chart does not install one. See [step 3](#3-put-a-sign-in-gateway-in-front) |

## 1. Create the secret

```bash
kubectl create namespace umbod
kubectl -n umbod create secret generic umbod-secrets \
  --from-literal=UMBOD_ROOT_SECRET="$(openssl rand -hex 32)" \
  --from-literal=UMBOD_OIDC_CLIENT_SECRET="$OIDC_CLIENT_SECRET"
```

Set `OIDC_CLIENT_SECRET` to the client secret from your OIDC provider first.

!!! warning "Never change the root secret"
    Umbod derives its encryption keys from `UMBOD_ROOT_SECRET`. Changing it invalidates issued credentials and makes saved connector credentials unreadable. Back it up.

## 2. Write the values file

Create `values.production.yaml`:

```yaml
existingSecret: umbod-secrets

config:
  profile: production
  authentication:
    mode: auth0                      # auth0, entra, or google
    oidc:
      domain: your-tenant.example.com
      clientId: your-client-id
      audience: https://umbod.example.com
      requiredScopes: openid,email,profile,groups
  authorization:
    adminGroup: admin                # members of this group are administrators
    adminMembershipClaim: https://umbod.example.com/claims/groups
    mcpPermissionClaim: https://umbod.example.com/claims/groups
  publicOrigins:
    site: https://umbod.example.com
    api: https://umbod.example.com
    mcp: https://umbod.example.com

persistence:
  enabled: true
  size: 1Gi

ingress:
  enabled: true
  className: nginx
  host: umbod.example.com
  tls:
    - secretName: umbod-tls
      hosts:
        - umbod.example.com
```

What to change:

| Value | Set it to |
| --- | --- |
| `config.authentication.oidc.*` | The domain, client ID, and API audience from your provider |
| `config.authentication.oidc.issuerUrl` | Required for `entra` and `google`. Entra also needs `UMBOD_OIDC_TENANT_ID` in both `core.api.env` and `core.mcp.env` |
| `config.authorization.adminGroup` | The group whose members administer Umbod |
| `config.authorization.*Claim` | The name of the token claim that lists a user's groups |
| `config.publicOrigins.*` | The addresses users and agents use. Scheme and host only, no `/api` or `/mcp` path |
| `persistence.enabled` | Keep `true`. Without it, all data is lost when the Pod restarts |
| `ingress.*` | Your ingress class, hostname, and TLS secret |

All values and defaults are in the [Helm values reference](../reference/helm-values.md).

## 3. Put a sign-in gateway in front

Agents sign in through Umbod's own OAuth flow on the MCP endpoint. Browsers do not: the workspace expects a gateway that signs users in with your OIDC provider and forwards their access token.

The gateway must:

1. Require a signed-in session for `/` and `/api`.
2. Forward the user's access token to Umbod in the `Authorization` header. To use another header, set `config.authorization.adminJwtHeader`.
3. Answer unauthenticated `/api` requests with `401`, not a redirect to a login page.
4. Keep the `Origin` header and cookies, and never return tokens to the browser.

Leave these routes open, without gateway sign-in. Umbod authenticates them itself:

| Route | Used for |
| --- | --- |
| `/mcp`, `/.well-known/oauth-*`, `/authorize`, `/token`, `/register`, `/revoke` | Agent sign-in |
| `GET /api/install/v1/codex/*` and `/api/install/v1/claude-code/*` | The agent installer |
| `POST /api/install/v1/*/telemetry/redeem` | Installer telemetry setup |
| `/api/oauth/downstream-mcp/callback` and below | Personal connector sign-in |
| `PUT /api/filesystem/uploads/{upload_id}/transfer` | File uploads from agents |

Do not add path rewrites to the ingress, and never expose `/v1/*` or ports `8001`, `8012`, `8013`, and `4318`.

A working oauth2-proxy and Traefik setup is in [`docker-compose.yml`](https://github.com/computerlovetech/umbod/blob/main/umbod/docker-compose.yml) in the repository.

## 4. Install

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version {{ release.chartVersion }} \
  --namespace umbod \
  --values values.production.yaml \
  --wait --timeout 5m
```

## 5. Check

1. Run the chart tests:

    ```bash
    kubectl -n umbod get pods
    helm -n umbod test umbod --logs --timeout 2m
    ```

    All Pods are `Running` and every test reports `Succeeded`.

2. Open `https://umbod.example.com` and sign in as a member of the administrator group. **Administration** is in the sidebar.
3. Sign in as a user outside that group. The workspace opens and **Administration** is absent.

If a check fails, see [Troubleshooting](troubleshooting.md).

## Next

1. [Schedule cleanup](operate.md#schedule-cleanup). The chart does not do it for you.
2. [Add a connector](../use/connectors.md) and [connect an agent](../use/connect-agents.md).
3. Optional: [store files in S3](s3.md) or [collect agent telemetry](telemetry.md).

## Uninstall

```bash
helm -n umbod uninstall umbod
```

This removes the chart's volume claim and, with most storage classes, the data in it. [Back up](operate.md#back-up-and-upgrade) first if you need it. The secret remains.
