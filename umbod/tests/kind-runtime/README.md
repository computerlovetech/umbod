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
- [run.sh](./run.sh) — Kind integration runner.
- [setup_personal_runtime.py](./setup_personal_runtime.py) — Verified-user runtime setup.
- [values.yaml](./values.yaml) — Test-only deployment values.
- [connector](./connector/) — Runtime connector fixture.

# Context not available from the code

- [Repository runtime verification instructions](../../../AGENTS.md#apimcp-runtime) — Kind is required for API and MCP application changes.
- The connector, identity fixture, bootstrap grant, test-only values and extra worker deployment must not enter the published chart or application images.
