---
type: Runbook
title: Website deployment
description: Separate Cloudflare preview and production Workers without GitHub deployment credentials.
---

# Website deployment

The default [Wrangler configuration](wrangler.jsonc) deploys `umbod-website` at
`umbod.ai`. The `preview` environment deploys `umbod-website-preview` at
`preview.umbod.ai`. Updating either Worker does not update the other.

No Cloudflare credentials or deployment jobs are added to GitHub Actions.
The release workflow does not yet deploy the website automatically.

## Cloudflare preview setup

1. Connect the `umbod-website-preview` application to the repository’s main
   branch. Keep the existing website build configuration and full-repository
   checkout needed for documentation.
2. For commands running from `website/`, use `bun run build` as the build
   command and `bunx wrangler deploy --env preview` as the deploy command.
   If the build root is the repository root, prefix each command with
   `cd website &&`. Disable non-main branch deployments unless separately configured.
3. Disable automatic main deployments on the production `umbod-website`
   application. Leave `umbod.ai` attached so its current deployment keeps serving.
4. Remove only `preview.umbod.ai` from the old application if it is still attached.
   The hostname must not belong to another Worker when preview first deploys.
5. Deploy the updated main configuration to the preview application. Its first
   successful deployment creates the preview Worker and applies the custom domain.
   Check domain and certificate status afterward. If manual attachment is still
   needed, add subdomain `preview` on the new application after deployment.
6. Check zone redirects do not send preview traffic to the production apex.

A newly connected application may not have a deployed Worker yet. If attaching
the domain reports that the Worker does not exist, verify the first successful
deployment before retrying.

Repository changes do not configure Cloudflare’s build commands, branch triggers,
or existing custom-domain ownership.

## Production

Keep production auto-builds from main disabled. To deploy a release manually,
check out the intended release tag, install locked website dependencies, and
build the website and documentation from that checkout. Deploy the resulting
build using `bunx wrangler deploy --env=""` from `website/` to select production
explicitly. `bun run deploy` also builds and deploys production, not preview.

Production is not automatically release-gated by this configuration. An operator
must select the release-tag checkout until release automation is added.

## Verification

Verify preview home, `/docs/`, `/enterprise/`, retired download redirects, assets,
and unknown-path 404 responses. Confirm a main deployment updates preview while
production remains unchanged. After an intentional production deployment, verify
the same routes on `umbod.ai`.
