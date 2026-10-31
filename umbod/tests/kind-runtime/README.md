---
type: Software Module
title: Kind runtime verification
description: Disposable-cluster runner and fixtures for serial API and MCP service integration checks.
---

# Files

- [bootstrap.py](./bootstrap.py) — Runtime setup.
- [check_secret_logs.py](./check_secret_logs.py) — Secret-log checks.
- [check_telemetry_logs.py](./check_telemetry_logs.py) — Telemetry-log checks.
- [personal_fixture.py](./personal_fixture.py) — Personal authentication fixture.
- [run.sh](./run.sh) — Disposable Kind runner; local by default, S3 with UMBOD_TEST_CONTENT_BACKEND=s3.
- [setup_s3_runtime.py](./setup_s3_runtime.py) — Test-only Moto S3 emulator, Secret, SDK bucket provisioning and in-cluster object inspection.
- [setup_personal_runtime.py](./setup_personal_runtime.py) — Verified-user runtime setup.
- [values.yaml](./values.yaml) — Test-only deployment values.
- [connector](./connector/) — Runtime connector fixture.

# Verification boundaries

- [Repository runtime verification instructions](../../../AGENTS.md#apimcp-runtime) — Kind is required for API and MCP application changes.
- [Test-only values](./values.yaml) — Fixtures, SDK credentials and bootstrap scripts stay outside published charts and application images.
- [S3 live coverage](../../api/live_runtime_tests/test_running_filesystem_s3.py) — Real-network multipart, publication, worker independence and immutable object checks.
