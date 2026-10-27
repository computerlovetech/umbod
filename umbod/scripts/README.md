---
type: Software Module
title: Repository scripts
description: Source README validation, release version conversion and SDK version stamping.
---

# Files

- [check_module_readmes.py](./check_module_readmes.py) — OKF frontmatter validation beneath source trees.
- [release_versions.py](./release_versions.py) — Release version conversion.
- [stamp_sdk_version.py](./stamp_sdk_version.py) — SDK build-workspace stamping.
- [tests](./tests/) — README checks, version and release workflow contracts.

# Context not available from the code

- [Release workflow](../../.github/workflows/umbod-release.yml) — SDK, image and Helm publication. Desktop releases remain independent.
- Configure the `umbod-pypi` GitHub environment deployment rules to permit `umbod-v*` tags; a main-branch-only rule blocks SDK publication.
- For a partial release, use GitHub **Re-run failed jobs** to retain successful plan and SDK outputs. Do not rerun all jobs or push another tag as a retry: published versions cannot be overwritten. If the original run cannot resume, reconcile registry state manually before choosing a new release tag.
