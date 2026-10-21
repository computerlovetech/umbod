# Umbod website

Website for Umbod, computerlove.tech's open-source agent infrastructure product.

The home page (`/`) introduces self-hosted Umbod to platform teams. Get started
leads to the local Kubernetes walkthrough at `/#how`; contact is secondary.
`/enterprise/` remains available with the same platform capabilities and onboarding.
See [website context](CONTEXT.md) for positioning and tone.

Update chart, image, and SDK release versions in the repository-root
[`release-metadata.json`](../release-metadata.json). MkDocs substitutes these values
in the guides and generated Helm reference; Vite substitutes them in the landing
page during development and build. Do not edit release tags in the rendered
`website/public/docs/` or `website/dist/` output.

Vite builds two HTML entries: `index.html` and `enterprise/index.html`. Shared
header/footer partials are inserted at build time, so navigation works without
JavaScript. `src/site.mjs` enhances the mobile menu and command-copy buttons.
Cloudflare Workers static assets serve `/enterprise/` and normalize `/enterprise`
to it using default HTML handling. `public/_redirects` redirects `/enterprise.html`
to `/enterprise/` and the retired `/download` and `/download/` routes to `/#how`.

## Development

Run these commands from `website/` with Bun and Python (including pip) available.
The development command installs `mkdocs-material==9.7.7` and builds the Umbod
MkDocs site into `/docs/`.

```bash
bun install
bun run dev
```

## Build

```bash
bun run build
```

The build installs only the documentation dependencies with
`python -m pip install "mkdocs-material==9.7.7"`, then runs
`python -m mkdocs build --strict --site-dir ../website/public/docs` from `umbod/`,
where `mkdocs.yml` lives. Vite then runs from `website/` and packages the complete
site into `website/dist/`. Python is needed only during the build; the deployed
website is static.

Build from a checkout that preserves the sibling `website/` and `umbod/`
directories. The build needs these inputs:

- `umbod/mkdocs.yml`
- `umbod/docs/`, including `hooks.py`
- `umbod/docs-theme/`
- `umbod/deploy/helm/umbod/Chart.yaml`, `values.yaml`, and `values.schema.json`,
  which the docs hook uses to generate the Helm values reference

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

## Verification

Run `bun run test` for route, content, shared navigation and release-version checks.
The tests build both entries in an isolated temporary checkout and launch local
Wrangler to verify Enterprise deep links, legacy redirects and real 404 responses.
No Cloudflare credentials are needed. Run `bun run build` before shipping.

Check `/`, `/enterprise`, `/enterprise/`, `/enterprise.html`, `/download`,
`/download/`, docs and asset links in local Wrangler. Inspect desktop and mobile
widths, including menu, command copying, keyboard focus and JavaScript-disabled
navigation. Get started should always reach the home page Kubernetes walkthrough.
