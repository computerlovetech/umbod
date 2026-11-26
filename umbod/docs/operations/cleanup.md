---
type: Operational Guide
title: Scheduled cleanup
description: Run all registered retention jobs through the operational CLI against the server's persistent database.
---

# Scheduled cleanup

Before rollout, schedule `umbod cleanup` hourly against the same SQLite database your servers use. Disable overlapping runs and alert on both failed and missed runs. Neither Docker Compose nor the Helm chart installs this schedule. Starting or restarting API and MCP, serving requests, and collecting background usage do not delete expired data.

Each invocation runs all cleanup jobs in the installed Umbod version once, in order. You cannot select individual jobs, and later versions can add jobs without changing the command.

## Deployment requirements

1. Use the same pinned application image and persistence configuration as the servers. Set `UMBOD_CONNECTOR_STORE=sqlite` and keep `UMBOD_DATA_DIR` and any explicit `UMBOD_CONNECTOR_STORE_SQLITE_PATH`. The command does not support in-memory persistence.
2. Mount the same database volume and preserve the working directory if the path is relative. A new empty volume or a different working directory will not clean the live database. Choose storage and worker placement that support the servers' SQLite locking. Do not mount a ReadWriteOnce volume into an incompatible worker placement.
3. Use the deployment's normal configuration and secret delivery. Keep secrets out of command arguments and scheduler logs. Monitor the command's exit status. It readies the database before running jobs and closes its database runtime before exiting, without starting HTTP or metrics listeners.

## Included jobs

- Usage retention deletes usage events and daily rollups strictly before the UTC retention cutoff. `UMBOD_PERSONAL_USAGE_RETENTION_DAYS` retains its default of 90 days, including the current UTC day. Cleanup also applies when new usage collection is disabled.
- Agent-behaviour retention drains expired diagnostic-report and deduplication-receipt batches. Existing expiry policies remain unchanged: reports expire after 30 days and receipts after 60 days. Expired reports remain hidden from reads even before physical deletion.

This command does not delete analytics telemetry, filesystem contents, orphan objects or incomplete multipart uploads.

## Failures and retries

Check the exit status and the sanitized outcome for each job. Exit status zero means every job completed; nonzero means configuration, startup, or execution failed. An ordinary failure does not stop later jobs, so a failed or timed-out run may already have deleted some data. The jobs do not share one transaction.

Set `UMBOD_CLEANUP_JOB_TIMEOUT_SECONDS` only if jobs need a different time budget. The default is 5 seconds per job; the value must be positive and finite, up to 3600 seconds.

Cleanup can still contend with normal server writes. After a failed run, retry with a bounded scheduler backoff rather than a tight loop; alert after repeated failures. Retention deletion can safely run again against the current cutoff. Do not enable raw exception messages or HTTP debug payloads to investigate failures. See [safe application diagnostics](application-diagnostics.md).
