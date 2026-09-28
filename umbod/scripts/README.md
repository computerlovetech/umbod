# Release scripts

- `release_versions.py` selects chart versions and synchronized SDK/image releases from published histories and checked-in bootstrap versions.
- `stamp_sdk_version.py` stamps the SDK project and the API's local SDK lock entry in an image build workspace without resolving dependencies.
- `tests/` verifies release selection and byte-preserving version stamping.

If an image job fails after the SDK or another image succeeds, use GitHub **Re-run failed jobs** to retain the successful plan and SDK outputs. Do not re-run all jobs or start a new dispatch to retry a partial release: published versions cannot be overwritten. If the original run cannot be resumed, stop and reconcile the registry state manually before selecting a new release version.
