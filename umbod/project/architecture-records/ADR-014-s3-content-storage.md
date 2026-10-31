# ADR-014: S3 Content Storage Behind the Existing Byte Port

- **Status:** Accepted
- **Scope:** Filesystem byte storage, configuration, and verification

## Decision

Add S3 as a sibling of the local and in-memory content adapters under filesystem infrastructure, following ADR-006. It implements the existing `ContentDriver` streaming put/get contract. Namespace nodes, upload sessions, ownership, and permissions remain in the application's existing database. Public content references retain only their opaque logical key and byte size; bucket names, credentials, endpoints, and object prefixes do not enter domain models or REST/MCP responses.

Both REST and MCP select content storage through the public infrastructure composition boundary. Local storage remains the operator default; programmatic in-memory configuration remains supported. Selecting S3 must not fall back to an in-memory adapter. The two applications and all workers sharing a database must use the same content backend, bucket, and prefix.

## Configuration and credentials

`UMBOD_FILESYSTEM_CONTENT_BACKEND` selects `local` or `s3`. S3 requires `UMBOD_FILESYSTEM_S3_BUCKET`. `UMBOD_FILESYSTEM_S3_REGION` defaults to `us-east-1`; `UMBOD_FILESYSTEM_S3_ENDPOINT_URL` is empty for AWS endpoint resolution or an explicit HTTP(S) endpoint for a compatible service. Endpoints cannot contain credentials, query strings, or fragments. `UMBOD_FILESYSTEM_S3_PREFIX` is empty or a canonical relative object-key prefix. `UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE` selects `auto`, `virtual`, or `path`.

Credentials belong to the standard AWS SDK provider chain, including environment credentials, profiles, and workload identity. No access-key, secret-key, session-token, or presigning credential fields are introduced in Umbod configuration. Deployment operators provision the bucket and its policy separately. No startup bucket creation, listing, or content migration occurs. Bucket encryption and any required KMS permissions remain deployment policy; the adapter does not set public ACLs or introduce client-managed encryption keys.

Existing Helm environment overrides and the shared existing Secret can supply identical configuration and SDK credentials to API and MCP containers. Workload identity may use an externally managed service account. S3 does not remove the database or its storage requirements, nor make SQLite a multi-replica production database.

## Streaming, immutability, and resource ownership

Use aiobotocore for asynchronous S3 I/O. Each operation owns its SDK client context; downloads additionally own their response body. These resources close on completion, failure, cancellation, and explicit early stream closure. There is no long-lived client requiring new application lifespan ownership and no caller-bound shared SDK state.

Object names combine the configured prefix with a server-generated canonical UUID-hex logical key. Reads validate logical keys before opening a client or issuing a request. Writes use conditional publication so an existing immutable object cannot be overwritten. Small and empty objects use a single put; larger objects use bounded multipart streaming rather than whole-file buffering or local spooling. Multipart uploads use bounded parts and reject requests exceeding the supported part count without publishing a reference.

The adapter validates returned upload identifiers, part receipts, and read lengths at its external boundary. SDK and storage-response errors are translated into the existing sanitized storage failure vocabulary. Errors from the incoming byte stream retain their original type after storage cleanup, so upload validation failures remain client errors rather than storage outages. Interrupted or rejected writes return no content reference. Once an upload identifier is known, failure and cancellation trigger best-effort multipart abort without replacing the primary error. Cancellation handling must not close resources while outstanding operations still use them.

As with local content, object publication is outside the database transaction. A lost publication response or failed namespace transaction may leave an immutable orphan; the adapter must not delete a potentially published object as compensation. Bucket lifecycle rules for abandoned multipart uploads are recommended because process termination, network uncertainty, or failed aborts cannot guarantee immediate reclamation. This change does not add garbage collection, physical deletion guarantees, quotas, or storage accounting.

## Transport and existing data

Upload-session initiation, authenticated byte transfer through Umbod, explicit completion, and authorized streaming downloads remain unchanged. S3 is only the low-level byte adapter. It does not issue presigned URLs, expose a browser transfer target, or add direct-storage multipart session contracts. The MCP upload/read tools reuse the same core lifecycle and limits.

Existing references do not identify a backend, bucket, or prefix. Changing those settings for a populated database without first moving the corresponding immutable objects makes existing content unavailable. Automatic local-to-S3 migration, dual reads, and fallback storage are deliberately excluded. Provision a new deployment or perform a separately planned migration preserving logical keys and sizes before switching all workers together.

## Verification

Adapter contract tests cover empty and binary content, exact sizes, independent instances, immutable publication, bounded multipart transfers, invalid keys, remote failures, cancellation, and early download closure. Composition tests verify explicit S3 selection in both REST and MCP without changing their contracts or eagerly accessing remote storage.

The disposable Kind runner supports a test-only S3-compatible service and pre-provisioned bucket. Existing service integration tests run against the S3 configuration, supplemented by multipart, empty-file, cross-worker, and object-prefix checks. Test storage workloads, credentials, and bucket setup remain outside the published chart and application image.

## Supporting material

- [ADR-006: Filesystem Storage Infrastructure Boundary](ADR-006-filesystem-infrastructure-boundary.md)
- [ADR-009: Transport-Neutral File Upload Sessions](ADR-009-transport-neutral-upload-sessions.md)
- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
