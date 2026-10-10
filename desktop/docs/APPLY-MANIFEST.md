# Apply a desktop download manifest safely

The release workflow emits `website-manifest-update`, containing `website/public/desktop-downloads.json` and these instructions, only after publishing succeeds. This artifact does not automatically modify, merge, or deploy the website.

From the monorepo root, with Node 22+:

```sh
# Extract the workflow artifact into a temporary directory first.
node website/scripts/verify-desktop-manifest.mjs /tmp/website-manifest-update/website/public/desktop-downloads.json
# After that verification succeeds, intentionally apply the same file:
node website/scripts/verify-desktop-manifest.mjs /tmp/website-manifest-update/website/public/desktop-downloads.json --apply
node --test website/tests/*.test.mjs
cd website && bun run build
```

The verifier uses anonymous HTTPS access to the exact `computerlovetech/umbod` desktop tag, rejects draft/non-prerelease releases and source-SHA mismatches, and downloads both published assets to check their sizes and SHA-256 values. It streams bytes to a hash without executing or installing anything. Network failures, private/unpublished releases, wrong assets and bad hashes leave the existing file unchanged. No GitHub token or browser credential is used. The --apply flag changes only website/public/desktop-downloads.json using a temporary file and rename.

Review the manifest diff, inspect both platform choices and the self-host fallback in the built page, then submit it through the normal PR process. Keep website deployment separate. The Vite build validates and renders the manifest for no-JavaScript visitors; browser enhancement only recommends a platform when architecture is sufficiently known. An Intel-looking Mac user agent does not prove Apple Silicon, and mobile/unsupported platforms receive no recommended download.

Until this process is complete, keep the checked-in `{ "schemaVersion": 1, "status": "unavailable" }` manifest. To withdraw downloads, restore that state and rebuild/redeploy through the normal website process. Do not use a Kubernetes release tag, repo-wide latest, invented URLs, a private repository, or credentials in the public JSON.
