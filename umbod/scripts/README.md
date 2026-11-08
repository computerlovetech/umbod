---
type: Software Module
title: Repository scripts
description: Backend pytest runner, README validation, release metadata checks, SDK version stamping and Codex plugin packaging.
---

# Files

- [README skill checks](../../skills/development/write-module-readme/SKILL.md) — Skill-owned README validation and post-edit checks.
- [run_tests.py](./run_tests.py) — Directory-targeted backend pytest runner with automatic workers, optional slow-phase reports and argument forwarding.
- [release_versions.py](./release_versions.py) — Release version conversion and committed metadata validation.
- [stamp_sdk_version.py](./stamp_sdk_version.py) — SDK build-workspace stamping.
- [build_codex_plugin.py](./build_codex_plugin.py) — Generates a deployment-specific Codex marketplace without changing client settings or embedding credentials.
- [tests](./tests/) — Pytest runner, README checks, version, release workflow, and installed Codex package-loader contracts.

# Operations

- [Release workflow](../../.github/workflows/umbod-release.yml) — Tag provenance, publication gates, artifact stamping, and production promotion.
- [Release skill](../../skills/development/release-umbod/SKILL.md) — Manual preparation, publication approval, verification, and partial-release recovery.
- [Website deployment](../../website/deployment.md) — Preview/production builds, version checks, and branch protection requirements.
- [Codex CLI installation](../docs/using-umbod/codex-plugin.md) — Package installation, account authentication, connection verification, and lifecycle instructions.
- [Canonical integration skills](../../skills/integrations/README.md) — Source guidance distributed by agent-client packages.
