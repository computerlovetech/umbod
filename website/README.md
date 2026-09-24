# Umbod website

Website for Umbod, computerlove.tech's open-source agent infrastructure product.

The single landing page serves platform teams, with local Kubernetes evaluation and
feedback as its main paths. See [website context](CONTEXT.md) for positioning and tone.
Cloudflare redirects the former `/enterprise`, `/enterprise/`, and `/enterprise.html`
URLs to `/` through `public/_redirects`.

## Development

Run these commands from `apps/umbod-website/`. The development command builds the Umbod MkDocs site into `/docs/`, so `uv` is also required.

```bash
bun install
bun run dev
```

## Build

```bash
bun run build
```

The build generates the Umbod reference documentation from `apps/umbod/docs/` and the Helm chart sources before Vite packages the complete site.

To check redirects and static assets with Cloudflare's local runtime after building:

```bash
bunx wrangler dev --port 8787
```

## Deploy to Cloudflare Workers

The Wrangler configuration publishes the built site and assigns `umbod.ai` as its
Cloudflare Worker custom domain.

```bash
bun install
bunx wrangler login
bun run deploy
```

The Cloudflare account used by Wrangler must contain the active `umbod.ai` zone.

## Redirect the other domains

In each of the `umbod.com` and `umbod.dev` Cloudflare zones:

1. Ensure the apex and `www` DNS records are proxied through Cloudflare.
2. Enable **SSL/TLS → Edge Certificates → Always Use HTTPS**.
3. Open **Rules → Redirect Rules → Single Redirects** and create permanent
   wildcard redirects with **Preserve query string** enabled:
   - `https://umbod.com/*` → `https://umbod.ai/${1}`
   - `https://www.umbod.com/*` → `https://umbod.ai/${1}`
   - Use the equivalent two rules for `umbod.dev`.
