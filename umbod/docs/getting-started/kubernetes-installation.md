# Kubernetes installation

Use Helm to install Umbod. Try it on your computer with kind, or skip to [setting up a shared installation](#configure-a-shared-installation) if you already have a Kubernetes cluster.

## Requirements

- Kubernetes 1.25 or newer
- Helm 3
- `kubectl`
- OpenSSL to generate the Umbod root secret
- Docker and kind for the recommended local installation

## Create a local cluster

=== "kind"

    Create a disposable cluster:

    ```bash
    kind create cluster --name umbod --wait 2m
    kubectl cluster-info --context kind-umbod
    ```

=== "minikube"

    Start minikube and select its context:

    ```bash
    minikube start --kubernetes-version=stable
    kubectl config use-context minikube
    ```

## Install Umbod locally

Make sure `kubectl config current-context` shows your local cluster. Create the Secret the first time you install Umbod. Keep the same Secret for upgrades: changing it invalidates credentials Umbod has already issued.

```bash
kubectl create secret generic umbod-secrets \
  --from-literal=UMBOD_ROOT_SECRET="$(openssl rand -hex 32)"
```

Install chart `{{ release.chartVersion }}` with Umbod images `{{ release.imageTag }}`. The `local` profile and `dev` authentication are for evaluation on your own computer only.

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version {{ release.chartVersion }} \
  --set existingSecret=umbod-secrets \
  --set config.profile=local \
  --set config.authentication.mode=dev \
  --set-string config.publicOrigins.site=http://localhost:3000 \
  --set-string config.publicOrigins.mcp=http://localhost:8011 \
  --wait --timeout 5m
```

In one terminal, make the Umbod web interface available on your computer:

```bash
kubectl port-forward service/umbod-frontend 3000:3000
```

In a second terminal, make the MCP endpoint available to local agents:

```bash
kubectl port-forward service/umbod-mcp 8011:8011
```

Keep both terminals running and open [http://localhost:3000](http://localhost:3000). To test with a local agent, add `http://localhost:8011/mcp` as a remote HTTP MCP server in the agent's settings. [Set up a connector](../using-umbod/connectors.md), publish its tools, and grant group access. Confirm that the agent can see the tools you've allowed.

An agent running elsewhere cannot reach your computer's `localhost`. For remote access, use HTTPS and production authentication.

## Validate the local installation

Check that the Pods are ready and the Services exist, then run the chart tests:

```bash
kubectl get pods,services
helm test umbod --logs --timeout 2m
```

## Configure a shared installation

Confirm that your current Kubernetes context is the cluster where you want to install Umbod. Create a namespace and a Kubernetes Secret. Replace the placeholder with the client secret from your OpenID Connect (OIDC) provider before running the command:

```bash
kubectl create namespace umbod --dry-run=client -o yaml | kubectl apply -f -
ROOT_SECRET="$(openssl rand -hex 32)"
kubectl -n umbod create secret generic umbod-secrets \
  --from-literal=UMBOD_ROOT_SECRET="$ROOT_SECRET" \
  --from-literal=UMBOD_OIDC_CLIENT_SECRET='replace-with-your-client-secret'
```

Create `values.production.yaml`:

```yaml
existingSecret: umbod-secrets

config:
  profile: production
  authentication:
    mode: auth0
    oidc:
      domain: your-tenant.example.com
      clientId: your-client-id
      audience: https://umbod.example.com
      requiredScopes: openid,email,profile,groups
  authorization:
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
```

Before installing:

- **HTTPS:** Set `ingress.tls` or use an HTTPS proxy in front of the Ingress. The chart does not set up TLS by default. Use the same addresses in `publicOrigins` that users and agents will use.
- **Sign-in:** Set the OIDC domain, client ID, audience, and group claims to match your provider. Set up an [external gateway for browser sign-in](../operations/service-topology.md#administration-api-clients); the chart does not install one.
- **Storage and images:** Confirm that the storage class is available and keep the image tags shipped with the chart.

See [Configuration](../operations/configuration.md) for what the settings do and the [Helm values reference](../reference/helm-values.md) for defaults.

To store file contents in an S3 bucket, follow [S3 file storage](../operations/s3-file-storage.md). Keep the application database on persistent storage even if you use S3.

Install or upgrade Umbod:

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version {{ release.chartVersion }} \
  --namespace umbod \
  --values values.production.yaml \
  --wait --timeout 5m
```

Validate the shared installation:

```bash
kubectl -n umbod get pods,services
helm -n umbod test umbod --logs --timeout 2m
```

Open the shared HTTPS address and sign in with an account in the administrator group. Check that you can open **Administration**. Then check that a signed-in non-administrator can open the workspace but cannot open **Administration**.

!!! warning
    The chart runs one copy of the core service with a SQLite database. Persistent storage keeps data when Kubernetes replaces the Pod, but it does not make Umbod highly available. Use this chart for development and evaluation.

## Upgrade from 0.0.1-beta.9

Back up the application database and file bytes together. Export any files outside registered namespaces before upgrading. Rehearse the upgrade on a copy; Umbod does not automatically migrate incompatible database schemas or move files into registered namespaces. Keep the root secret unchanged, and upgrade API, MCP, and frontend together.

- Move administrator clients to the [private MCP listener](../operations/configuration.md#administrator-mcp-hosting). Rediscover the available tools and update scripts to use `admin_discover`, `admin_inspect`, and `admin_apply`.
- For file automation, use MCP `resources/read` instead of `filesystem_read_file`. New folder grants made through `filesystem_share` are recursive by default; pass `recursive: false` for a grant on the folder alone. Review the [current tool contracts](../reference/built-in-tools.md) before reusing older requests.
- If you collect OTLP telemetry, remove any public `/v1/*` route and point exporters at the [private collector](../operations/telemetry-ingestion.md). Enable analytics storage separately if you need to query logs.
- Check that users can still reach their files after the upgrade. Files outside registered namespaces are not visible, but their stored bytes are not deleted. See [Filesystem access](../using-umbod/files.md#personal-and-shared-files).

## Uninstall

Remove the local release and kind cluster. Deleting the cluster also removes data stored only in that cluster:

```bash
helm uninstall umbod
kind delete cluster --name umbod
```

For a namespaced installation, remove the release without deleting the cluster:

```bash
helm --namespace umbod uninstall umbod
```
