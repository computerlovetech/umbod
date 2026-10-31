---
type: Software Module
title: Repository scripts
description: Source README validation, release version and metadata checks, and SDK version stamping.
---

# Files

- [README skill checks](../../skills/development/write-module-readme/SKILL.md) — Skill-owned README validation and post-edit checks.
- [release_versions.py](./release_versions.py) — Release version conversion and committed metadata validation.
- [stamp_sdk_version.py](./stamp_sdk_version.py) — SDK build-workspace stamping.
- [tests](./tests/) — README checks, version and release workflow contracts.

# Operations

- [Release workflow](../../.github/workflows/umbod-release.yml) — Tag provenance, publication gates, artifact stamping, and production promotion.
- [Release skill](../../skills/development/release-umbod/SKILL.md) — Manual preparation, publication approval, verification, and partial-release recovery.
- [Website deployment](../../website/deployment.md) — Preview/production builds, version checks, and branch protection requirements.
