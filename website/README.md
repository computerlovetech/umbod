# Umbod website

Website for Umbod, computerlove.tech's open-source agent infrastructure product.

The home page (`/`) serves individuals evaluating Umbod Desktop, with download
availability as the primary path. `/enterprise/` serves platform teams evaluating
self-hosted Umbod, with contact and installation docs as its conversion paths.
See [website context](CONTEXT.md) for positioning and tone.

Update chart, image, and SDK release versions in the repository-root
[`release-metadata.json`](../release-metadata.json). MkDocs substitutes these values
in the guides and generated Helm reference; Vite substitutes them in the landing
page during development and build. Do not edit release tags in the rendered
`website/public/docs/` or `website/dist/` output.

Vite builds two HTML entries: `index.html` and `enterprise/index.html`. Shared
header/footer partials are inserted at build time, so both pages work without
JavaScript. `src/site.mjs` enhances the mobile menu and command-copy buttons.
Cloudflare Workers static assets serve `/enterprise/` and normalize `/enterprise`
to it using default HTML handling. `public/_redirects` only redirects the legacy
`/enterprise.html` URL to `/enterprise/`; neither enterprise URL redirects home.

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

The desktop source/build links use an immutable public source revision while this
PR is unmerged; `main/desktop` currently returns 404. Update that revision when the
desktop instructions change, or use `main` after it contains the desktop tree.

## Desktop downloads

The home-page download CTAs use `public/desktop-downloads.json`, independently of
root release metadata. Enterprise navigation returns to `/#downloads` and never
initializes desktop downloads. The initial state is unavailable, with self-hosting
explicitly labeled as a separate edition for teams;
do not add speculative URLs. `src/downloads.mjs` validates exact desktop tags, public
asset URLs, hashes and platform choices. Vite renders a no-JavaScript fallback from the
same validated manifest. Run `bun run test` for download, manifest-update and
route/content tests. The route tests build both entries in isolated temporary
checkouts with available and unavailable manifests, checking metadata, navigation,
anchors and no-JavaScript download links without changing the working manifest.
They also launch local Wrangler on a temporary loopback port to verify enterprise
deep links and a real 404 for unknown routes. No Cloudflare credentials are needed.

Before shipping, run the full build and use local Wrangler to check `/`,
`/enterprise`, `/enterprise/`, `/enterprise.html`, docs and asset links. Inspect
both pages at desktop and mobile widths, including the menu, keyboard focus,
download state and JavaScript-disabled navigation. Do not advertise a release
until the manifest procedure below succeeds.

Follow [the manifest application procedure](../desktop/docs/APPLY-MANIFEST.md) to
verify published assets and prepare the website PR. No frontend credentials are used.
