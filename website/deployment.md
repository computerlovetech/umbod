---
type: Runbook
title: Website preview deployment
description: Use the existing Cloudflare Git integration to deploy main to preview.
---

# Website preview deployment

The default [Wrangler configuration](wrangler.jsonc) deploys the
`umbod-website-preview` Worker at `preview.umbod.ai`. The existing Cloudflare Git
integration handles building and deploying main. No Cloudflare credentials or
deployment jobs are added to GitHub Actions.

The existing production Worker, `umbod-website`, remains configured under the
explicit `production` environment at `umbod.ai`. Release-tag production
automation is deferred; the release workflow does not deploy the website.

## Cloudflare setup

1. Create or select the `umbod-website-preview` Worker and connect the same
   repository and main branch using the existing website build configuration.
   Keep the website root directory and existing build and deploy commands.
   Deploy without an environment flag so Wrangler selects the default preview.
2. Disconnect the main build trigger from `umbod-website`, but do not delete the
   Worker or detach `umbod.ai`. Keep its current production deployment serving.
   Cloudflare’s connected Worker must match the new default Worker name; changing
   Wrangler alone does not move the Git integration to another Worker.
3. Ensure no conflicting DNS record or Worker route owns `preview.umbod.ai`.
   The first preview Wrangler deployment provisions the custom domain, DNS, and
   certificate in the account containing the active `umbod.ai` zone.
4. Check zone redirects do not send preview traffic to the production apex.

These settings must be applied in Cloudflare; repository changes do not update
the connected Worker, existing build triggers, or confirm DNS activation.

## Verification

After deployment, verify preview home, `/docs/`, `/enterprise/`, retired download
redirects, assets, and unknown-path 404 responses. Confirm a subsequent main
update changes preview without changing production.

Local `bun run deploy` also targets preview. Production requires explicitly
selecting the `production` Wrangler environment. Do not use that environment
in the main branch Cloudflare build configuration.
