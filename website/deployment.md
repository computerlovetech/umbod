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
- Release preflight rejects tags whose committed `release-metadata.json` does not
  match the chart, image, and SDK versions derived from that tag, before publication.
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
Ordinary releases validate committed `release-metadata.json` against the tag's
chart, image, and SDK versions without rewriting it. Update metadata on main before
creating the tag, so preview and production builds use the same release versions.
Missing, malformed, ambiguous tags or mismatched metadata fail the build.

A one-time production bootstrap may carry `website/release-source.tag` when the
latest existing release predates the deployment setup. The bootstrap must be a
single commit directly above that tag and may change only the website package
manifest, Wrangler configuration, release preparation script, and tag marker.
Only this legacy bootstrap stamps build-local metadata from its source tag.
Released pages and documentation cannot change. Main records the bootstrap commit
as an ancestor without importing its tag marker, so the next release can advance
production with a normal fast-forward push.

The promotion does not commit generated metadata or website output. Ordinary
promotions point `production` at the exact verified release commit with matching
committed metadata; the one-time bootstrap described above adds only deployment
files. Preview uses main's committed metadata and can advance independently after
a release, but its version must not differ merely because the build command differs.

## Promotion safety and recovery

Only the release workflow should update `production`; do not push to it manually.
The `production-history-protection` GitHub ruleset blocks branch recreation,
deletion and non-fast-forward updates with no bypass actors. It does not block
ordinary human fast-forward pushes.

Strict update-actor enforcement is not yet configured. GitHub rejected its built-in
Actions identity as a ruleset bypass actor, so the current built-in token cannot
be used to claim workflow-only branch protection. Completing that protection
requires an installed, dedicated GitHub App and a short-lived token issued only
to the approved release-promotion job; protect the credential and workflow-change
approval boundary as well. Restrict updates to that app without human/admin
bypass, while retaining the separate no-bypass history ruleset. A bypass app
identifies an actor, not a workflow path; stricter workflow identity requires
credential issuance bound to that workflow. Do not lock all updates without first
provisioning and verifying the authorized promotion identity.

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
