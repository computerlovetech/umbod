# Umbod website

Website for Umbod, computerlove.tech's open-source agent infrastructure product.

The single landing page serves platform teams, with local Kubernetes evaluation and
feedback as its main paths. See [website context](CONTEXT.md) for positioning and tone.

Update chart, image, and SDK release versions in the repository-root
[`release-metadata.json`](../release-metadata.json). MkDocs substitutes these values
in the guides and generated Helm reference; Vite substitutes them in the landing
page during development and build. Do not edit release tags in the rendered
`website/public/docs/` or `website/dist/` output.

Cloudflare redirects the former `/enterprise`, `/enterprise/`, and `/enterprise.html`
URLs to `/` through `public/_redirects`.

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

## Desktop downloads

Both landing-page download CTAs use `public/desktop-downloads.json`, independently of
root release metadata. The initial state is unavailable with a self-hosting alternative;
do not add speculative URLs. `src/downloads.mjs` validates exact desktop tags, public
asset URLs, hashes and platform choices. Vite renders a no-JavaScript fallback from the
same validated manifest. Run `bun run test` for download and manifest-update tests.

Follow [the manifest application procedure](../desktop/docs/APPLY-MANIFEST.md) to
verify published assets and prepare the website PR. No frontend credentials are used.
