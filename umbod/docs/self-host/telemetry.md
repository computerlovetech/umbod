---
description: Turn on the private OTLP collector and log analytics so agents can send logs to Umbod.
---

# Collect telemetry

Let agents send their logs to Umbod so you can see what they do in [Insights](../use/insights.md). Collection is off by default.

!!! warning "Logs can contain prompts and personal data"
    Umbod stores what agents send and does not redact it. Decide who may see it and how long you keep it before you turn this on.

## Turn it on

1. Create a secret with an ingestion token:

    ```bash
    kubectl -n umbod create secret generic umbod-telemetry \
      --from-literal=UMBOD_OTLP_BEARER_TOKEN="$(openssl rand -hex 32)"
    ```

2. Add to your values file:

    ```yaml
    telemetry:
      enabled: true
      publicBaseUrl: https://telemetry.example.com   # the address agents reach the collector at
      bearerTokenSecret:
        name: umbod-telemetry

    config:
      telemetryAnalytics:
        enabled: true
    ```

3. Run the `helm upgrade --install` command from [Install](install.md#4-install) again.
4. Make the collector reachable for your agents at `publicBaseUrl`, over HTTPS. It is the `umbod-telemetry` Service on port `4318`. Keep it off the public Umbod ingress.

`telemetry.enabled` turns on the collector. `config.telemetryAnalytics.enabled` stores the logs so the reports in [Insights](../use/insights.md) work. `publicBaseUrl` only tells the installer where to point agents.

## Connect agents

The simplest way: users install their agent [with telemetry](../use/connect-agents.md#send-agent-logs-to-umbod). Their logs are then attributed to them.

To configure an exporter by hand:

| Setting | Value |
| --- | --- |
| Protocol | OTLP over HTTP, JSON or protobuf. gRPC is not supported |
| Endpoints | `/v1/logs`, `/v1/metrics`, `/v1/traces` |
| Authorization | `Bearer <token>`: the ingestion token, or a user's [personal access token](../reference/rest-api.md#personal-access-tokens) |
| Maximum request size | 10 MiB |

Logs sent with the shared ingestion token are not attributed to a user. Only logs are stored for reports. Metrics and traces go to the collector's standard output.

**Check:** send one test log and expect `200`. It then shows up in **Administration → Insights → Log analytics**.

| Response | Cause |
| --- | --- |
| `401` | Wrong or missing token |
| `413` | Batch too large |
| `415` | Wrong content type or encoding |

## Raw log archive

To keep the original log batches so you can reprocess them, set `UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED=true` in `core.api.env`. Batches are kept for 30 days (`UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS`).

Reprocess a period with `umbod telemetry backfill --from <time> --to <time>`. It previews by default. Add `--apply` to rewrite the stored logs.

## Mark your own activity

Agents that are not Claude Code or Codex can label their logs so the reports recognize them:

| Attribute | Values |
| --- | --- |
| `umbod.activity.kind` | `tool_call`, `file_read`, `file_edit`, `skill_activation` |
| `umbod.activity.outcome` | `success`, `failure`, `unknown` |
