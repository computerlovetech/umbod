---
type: Feature Specification
title: Replayable telemetry log archive
description: Preserve original OTLP log batches for controlled reprocessing without exposing raw data in analytics.
---

# Replayable telemetry log archive

## Capture

- Given archiving is enabled alongside telemetry analytics, when Umbod accepts a nonempty `/v1/logs` request, it saves one archive entry containing the validated request bytes after HTTP decompression, their JSON or Protobuf encoding, the server receipt time, and the ownership established by authentication. OTLP timestamps and identity claims do not determine archive retention or ownership.
- Each unified row links to a server-generated, non-reused batch ID and its zero-based position in OTLP resource/scope/record order. Store no transport headers or credentials. Raw and unified writes commit in one transaction. If either write fails, neither is committed and the receiver returns `503`. Existing stdout delivery still precedes database persistence and is not part of that transaction. Producer retries remain distinct exports.
- With archiving disabled, processing is unchanged. Rejected requests, empty exports, metrics, and traces do not create archive entries. Historical analytics rows are not backfilled.

## Access and retention

- Archiving is on by default in development Docker Compose when analytics is enabled, and off by default elsewhere. The default retention is 30 days, configurable independently of analytics. An archive becomes ineligible for replay at its expiry cutoff; cleanup runs at startup and hourly while analytics is active, even when ingestion is idle. Disabling capture stops new archives but does not prevent expiry of existing archives.
- Expiry leaves unified rows, their ownership, and analytics counts intact. Backup and snapshot retention are separate operational responsibilities; deleting a database row is not a promise to erase all copies.
- Raw telemetry can contain private data. Do not expose it in analytics queries, the browser, errors, or new diagnostic logs. Replay access is restricted to operators with access to the archive database; existing stdout delivery has its own access and retention policy.

## Replay

- Given an unexpired archive, preview runs the selected normalizer against the source bytes using the saved encoding, receipt time, and trusted owner. Normalizers must return one output per source record in the original order. Preview reports only safe metadata and counts, does not return source data, and does not write.
- Apply replaces only that batch’s unified rows in one transaction. It rechecks archive availability inside that transaction; expiry or any parsing, normalization, or write failure leaves the current unified rows intact. Applying the same normalizer twice does not append duplicates. Replay does not emit a new collector export or accepted-log observation. A caller interrupted during commit may not know whether the transaction committed; neither ingestion nor replay can commit a partial batch.
- Keep preview and apply independent of request or terminal handling. There is no HTTP replay endpoint, and this feature does not change skill-name normalization.

## Operator backfill

- The server CLI command `umbod telemetry backfill` selects either one `--batch-id` or a UTC receipt-time window (`--from` inclusive, `--to` exclusive; timestamps must carry an offset). It opens the server's configured analytics database, requires an existing compatible archive schema, and never migrates, creates, or sweeps that database.
- Preview is the default and opens SQLite read-only. `--apply` allows writes. Time windows select only retained batches, in receipt-time and then batch-ID order. A bounded selection that exceeds its limit fails before any replay; an empty window succeeds with no changes. A missing or expired explicitly selected batch fails.
- Each apply commits independently. On the first failure, stop and report the failed batch and how many batches already committed; do not roll back earlier batches. Running the same selection again does not append duplicates. Report only batch IDs, times, counts, and safe status messages; do not output raw payloads or use stdout logs to reconstruct missing archives.

## Delivery and verification

1. Add the typed atomic write contract and SQLite migration. Verify exact bytes, stable record positions, legacy rows, and rollback of both writes.
2. Wire opt-in ingestion and expiry together. Verify capture for JSON and Protobuf, default-off behavior, unchanged counts after expiry, and deployed service configuration before enabling it.
3. Add preview and apply behind an application interface. Verify ownership and receipt-time preservation, expiry and rollback, and that replaying a Codex batch twice leaves counts unchanged. `skill.name` must remain recoverable in the raw archive and absent from the current unified projection.
