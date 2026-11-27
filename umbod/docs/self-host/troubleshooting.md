---
description: Fix a failing Umbod installation and trace a failed request or tool call through the logs.
---

# Troubleshooting

Commands assume the `umbod` namespace and release name.

## Get the facts

```bash
kubectl -n umbod get pods
kubectl -n umbod describe pod -l app.kubernetes.io/component=core
kubectl -n umbod logs deploy/umbod-core -c api
kubectl -n umbod logs deploy/umbod-core -c mcp
kubectl -n umbod exec deploy/umbod-core -c api -- umbod config validate
```

## Installation

| Symptom | Cause and fix |
| --- | --- |
| Core Pod does not start | A required setting is missing. Read the `api` and `mcp` logs: the first error names the variable. Most often `UMBOD_ROOT_SECRET` or an OIDC value |
| Core Pod is stuck in `Init` | A [connector plugin](../extend/build-a-connector.md#if-the-pod-does-not-start) failed to load |
| Data is gone after a restart | `persistence.enabled` is `false` |
| Browser sign-in loops, or the workspace shows errors after sign-in | The [gateway](install.md#3-put-a-sign-in-gateway-in-front) redirects `/api` instead of answering `401`, or does not forward the access token |
| Signed in, but **Administration** is missing | The user is not in `config.authorization.adminGroup`, or `adminMembershipClaim` does not name the claim your provider puts groups in |
| Redirects go to the wrong address | `config.publicOrigins` does not match the address users open |
| Agent sign-in fails | The gateway protects `/mcp` or the [open routes](install.md#3-put-a-sign-in-gateway-in-front), or `publicOrigins.mcp` is wrong |
| Agent signs in but sees no tools | Access is missing. See [why a user cannot see a tool](../use/connectors.md#when-a-user-cannot-see-or-use-a-tool) |

## Trace a failed request

1. Find the `X-Request-ID` header of the failing response. `X-Umbod-Version` and `X-Umbod-Revision` identify the build.
2. Search the logs for that request ID.
3. Read these fields on the matching record:

    | Field | Tells you |
    | --- | --- |
    | `mcp.failure.category`, `.origin`, `.stage`, `.reason` | What failed and where |
    | `mcp.downstream.response_received` | Whether the connected service answered |
    | `mcp.downstream.http.status_code` | The connected service's status, not Umbod's |
    | `oauth.stage`, `oauth.reason` | Where a Personal connector sign-in failed |

Rejected requests (validation, permissions) log at `WARNING`. Unexpected failures log at `ERROR`.

Do not repeat a write because its response failed. The write may have gone through.

## What Umbod keeps out of logs

Application logs never contain credentials, request or response bodies, tool arguments or results, OAuth callback queries, personal data, or signed URLs. Debug logging does not change this. Apply the same rule to your gateway and log pipeline.

[Telemetry](telemetry.md) is different: it stores what agents send, unredacted.
