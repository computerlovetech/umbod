---
description: Run Umbod on your own computer with kind and Helm in about five minutes.
---

# Try it locally

Run Umbod in a disposable Kubernetes cluster on your computer. This setup uses development sign-in and is for evaluation only.

## Before you start

You need Docker, [kind](https://kind.sigs.k8s.io/), Helm 3, `kubectl`, and OpenSSL.

## Install

1. Create a cluster:

    ```bash
    kind create cluster --name umbod --wait 2m
    ```

2. Create the root secret:

    ```bash
    kubectl create secret generic umbod-secrets \
      --from-literal=UMBOD_ROOT_SECRET="$(openssl rand -hex 32)"
    ```

3. Install the chart:

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

4. Forward the workspace and the MCP endpoint. Run each command in its own terminal and keep both running:

    ```bash
    kubectl port-forward service/umbod-frontend 3000:3000
    ```

    ```bash
    kubectl port-forward service/umbod-mcp 8011:8011
    ```

**Check:** `helm test umbod --logs --timeout 2m` passes, and [http://localhost:3000](http://localhost:3000) opens the workspace.

## Next

1. [Add a connector](../use/connectors.md) and grant a group access.
2. Add `http://localhost:8011/mcp` to your agent as a remote HTTP MCP server. See [Connect an agent](../use/connect-agents.md).

Agents on other machines cannot reach your `localhost`. For that, [install for a team](install.md).

## Remove

```bash
kind delete cluster --name umbod
```

This deletes all data in the cluster.
