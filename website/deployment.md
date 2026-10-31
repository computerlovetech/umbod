---
type: Runbook
title: Website deployment
description: Cloudflare main-branch preview and release-promoted production branch deployments.
---

# Website deployment

The default [Wrangler configuration](wrangler.jsonc) deploys `umbod-website` at
`umbod.ai`. The `preview` environment deploys `umbod-website-preview` at
`preview.umbod.ai`. Cloudflare’s Git integration builds and deploys both Workers.

- Preview watches `main`.
- Production watches `production`.
- After SDK, all images, and the Helm chart publish successfully, the
  [release workflow](../.github/workflows/umbod-release.yml) validates the release
  website and advances `production` to the verified release-tag commit.
- Both stable and beta `umbod-v*` releases promote production.
- No Cloudflare API token, account secret, or GitHub deployment environment is
  required. The promotion job uses GitHub’s built-in token with `contents: write`.

## Cloudflare build settings

Both applications use `website` as the root directory, with the full repository
available for documentation builds. Disable deployments from other branches.
Do not filter production builds to website paths: an application-only release must
still rebuild the website with the new release’s installation versions.

| Setting | Preview app | Production app |
| --- | --- | --- |
| Worker | umbod-website-preview | umbod-website |
| Watched branch | main | production |
| Build command | bun install --frozen-lockfile && bun run build | bun install --frozen-lockfile && bun run build:release |
| Deploy command | bunx wrangler deploy --env preview | bunx wrangler deploy --env="" |
| Custom domain | preview.umbod.ai | umbod.ai |

Keep each custom domain attached only to its corresponding Worker. Check zone
redirects do not send preview traffic to the production apex.

The first successful release containing this workflow creates `production` if
it does not exist. Once it exists, select it in Cloudflare and trigger its first
build if the earlier push was not observed. Do not initialize it from an arbitrary
main commit: production builds require an exact release tag.

Repository changes do not alter Cloudflare’s branch settings, build commands, or
custom-domain ownership. Production’s existing deployment remains serving until
a successful Cloudflare deployment replaces it.

## Release build versions

[Release preparation](scripts/prepare-release.sh) fetches Umbod tags from origin
and requires exactly one canonical `umbod-v*` tag on the checked-out commit.
It stamps build-local `release-metadata.json` with tag-derived chart, image, and SDK
versions before building. Missing, malformed, or ambiguous release tags fail the
build rather than deploying unversioned content.

A one-time production bootstrap may carry `website/release-source.tag` when the
latest existing release predates the deployment setup. The bootstrap must be a
single commit directly above that tag and may change only the website package
manifest, Wrangler configuration, release preparation script, and tag marker.
Released pages and documentation cannot change. Main records the bootstrap commit
as an ancestor without importing its tag marker, so the next release can advance
production with a normal fast-forward push.

This keeps installation instructions aligned with the release even when committed
metadata names an older version. The promotion does not commit generated metadata
or website output: `production` points at the exact verified release commit.
Preview’s ordinary build continues to use committed metadata.

## Promotion safety and recovery

Configure GitHub branch rules so the release workflow can update `production`;
keep direct human or unrelated automation pushes restricted. No custom token
needs to be created, but repository or organization policy must allow the job’s
built-in token to write repository contents.

Promotions serialize and use a normal, non-forced Git push. An older release
cannot replace a newer production branch tip if that would require moving it
backward or onto a divergent history. Do not force-update `production` during
ordinary releases.

The first automated release must tag a main commit containing the updated
workflow and build script with successful Umbod CI. Existing release tags are not
retroactively promoted.

If promotion fails after artifact publication, rerun only the failed website
promotion job, not the whole release: publication preflight rejects existing
versions. If Cloudflare’s subsequent build fails, retry that build in Cloudflare.
A successful promotion job confirms the branch update, not successful deployment;
inspect the separate Cloudflare build result.

For an emergency website rollback, select an earlier production deployment in
Cloudflare without changing the preview Worker or moving the production branch
backward. Local `bun run deploy` bypasses branch promotion and should be reserved
for explicit operator recovery.

## Verification

Confirm `production` points at the release tag’s verified commit. Verify the
Cloudflare production build uses that commit and its logs identify
`umbod-website`. Check home, `/docs/`, `/enterprise/`, legacy redirects, assets,
and unknown-path 404 responses on both domains.

Confirm a later main push updates preview without updating production. On the
next successful release, verify production changes and the website installation
instructions name that release.
