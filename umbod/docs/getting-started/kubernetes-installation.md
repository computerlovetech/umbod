# Kubernetes installation

Install Umbod from its OCI Helm chart. Start with kind for a local evaluation, or use the chart on an existing Kubernetes cluster.

## Requirements

- Kubernetes 1.25 or newer
- Helm 3
- `kubectl`
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

Install the `0.0.1-beta.2` beta with development authentication:

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version 0.0.1-beta.2 \
  --set config.profile=local \
  --set config.authentication.mode=dev \
  --wait --timeout 5m
```

Forward the frontend Service:

```bash
kubectl port-forward service/umbod-frontend 3000:3000
```

Open [http://localhost:3000](http://localhost:3000). Keep the port-forward process running while using Umbod.

## Validate the local installation

Inspect the workloads and run the chart tests:

```bash
kubectl get pods,services
helm test umbod --logs --timeout 2m
```

## Configure a shared installation

Create a namespace and the required Secret. Replace the OIDC client secret before running the command:

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

Review the [generated Helm values reference](../reference/helm-values.md) before installing. In particular, confirm the ingress class, public origins, OIDC claims, storage class, and immutable image tags.

Install or upgrade Umbod:

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version 0.0.1-beta.2 \
  --namespace umbod \
  --values values.production.yaml \
  --wait --timeout 5m
```

Validate the shared installation:

```bash
kubectl -n umbod get pods,services
helm -n umbod test umbod --logs --timeout 2m
```

!!! warning
    The chart currently runs a single core replica backed by SQLite. Persistent storage preserves data across Pod replacements, but this remains a development and evaluation architecture rather than a production database architecture.

## Uninstall

Remove the local release and kind cluster:

```bash
helm uninstall umbod
kind delete cluster --name umbod
```

For a namespaced installation, remove the release without deleting the cluster:

```bash
helm --namespace umbod uninstall umbod
```
