---
type: Operational Guide
title: Scheduled cleanup
description: Run all registered retention jobs through the operational CLI against the server's persistent database.
---

# Scheduled cleanup

`umbod cleanup` runs all cleanup jobs registered by the installed Umbod version once, sequentially. The job list is maintained in application composition; operators do not select individual jobs. Later versions can extend that list without changing the command.

API and MCP server startup, request processing and background usage collection do not run retention cleanup. Deploying this change therefore requires an external cleanup schedule to retain physical data deletion.

## Included jobs

- Usage retention deletes usage events and daily rollups strictly before the UTC retention cutoff. `UMBOD_PERSONAL_USAGE_RETENTION_DAYS` retains its default of 90 days, including the current UTC day. Cleanup also applies when new usage collection is disabled.
- Agent-behaviour retention drains expired diagnostic-report and deduplication-receipt batches. Existing expiry policies remain unchanged: reports expire after 30 days and receipts after 60 days. Expired reports remain hidden from reads even before physical deletion.

This command does not delete analytics telemetry, filesystem contents, orphan objects or incomplete multipart uploads.

## Deployment requirements

Run the command from the same pinned application image as the servers, with their application persistence configuration and access to the same database volume. Set `UMBOD_CONNECTOR_STORE=sqlite`; preserve `UMBOD_DATA_DIR` and any explicit `UMBOD_CONNECTOR_STORE_SQLITE_PATH`. A new empty volume or a different relative working directory does not clean the running deployment's database. In-memory persistence is not supported by this operational command.

Preserve normal configuration and secret delivery without placing secrets in command arguments or scheduler logs. The command prepares persistence through the normal readiness boundary and closes its runtime before exiting. It does not start HTTP servers or metrics listeners.

Configure an external scheduler to run `umbod cleanup` hourly, with overlapping invocations disabled and exit-status monitoring enabled. For SQLite, use storage and placement that support the same database file and locking semantics as the servers. Do not mount a ReadWriteOnce volume into an incompatible worker placement.

Neither Docker Compose nor the Helm chart installs a cleanup schedule automatically. An operator-managed task is required before rollout; restarting the servers is not a substitute. Monitor missed runs as well as failed runs to prevent unnoticed data growth.

## Failures and retries

Each job has a bounded execution budget: `UMBOD_CLEANUP_JOB_TIMEOUT_SECONDS` defaults to 5 seconds and accepts positive finite values up to 3600 seconds. An ordinary job failure does not prevent later jobs from running. A failed or timed-out invocation can have committed partial cleanup; the command does not promise an all-jobs transaction. Inspect the per-job outcome and sanitized structured failure diagnostics. Exit status zero means all registered jobs completed; a nonzero exit means configuration, initialization or execution failed.

Cleanup can still contend with normal server writes. After a failed run, retry with a bounded scheduler backoff rather than a tight loop; alert after repeated failures. Retention deletion can safely run again against the current cutoff. Do not enable raw exception messages or HTTP debug payloads to investigate failures. See [safe application diagnostics](application-diagnostics.md).
