---
type: Runbook
title: Website deployment
description: Deploy main to both website domains using the existing Cloudflare Git integration.
---

# Website deployment

The [Wrangler configuration](wrangler.jsonc) assigns both `umbod.ai` and
`preview.umbod.ai` to the existing `umbod-website` Worker. Both domains serve the
same deployment from main through the existing Cloudflare Git integration.

No Cloudflare credentials or deployment jobs are added to GitHub Actions.
Release-tag website deployment is deferred; the release workflow does not deploy
the website.

## Cloudflare setup

1. Keep the existing repository integration for main on `umbod-website`, with
   the existing website build and deploy commands. Do not select a separate
   Wrangler environment.
2. Ensure no conflicting DNS record or other Worker owns `preview.umbod.ai`.
   If a separate preview Worker was configured, disconnect its main builds and
   move the preview custom domain to `umbod-website` before deploying.
3. The next Wrangler deployment applies both custom domains in the account
   containing the active `umbod.ai` zone. Check preview DNS and certificate
   activation after deployment.
4. Check zone redirects do not send preview traffic to the production apex.

Repository changes do not confirm the Cloudflare integration settings or DNS
activation.

## Verification

After deployment, verify both domains serve the same home page, `/docs/`,
`/enterprise/`, retired download redirects, assets, and unknown-path 404
responses. Subsequent main deployments update both domains together.

Local `bun run deploy` also updates both domains on the same Worker.
