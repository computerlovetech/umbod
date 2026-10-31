---
type: Release Verification
title: Umbod release checks
description: Required evidence and commands for release preparation, publication, and live deployment.
---

# Umbod release checks

Run commands from the stated repository directory. Read current `AGENTS.md` and workflows first; stop and reconcile drift. Use Bun for JS packages and uv for Python. SDK/application tests require their declared Python versions; website CI uses Python 3.12 with pip, Node 22 and Bun 1.4.2. Docker, Kind, Helm and the chart validator's dependencies are needed for applicable runtime/deployment checks.

## Before creating the tag

Record each result against the final candidate SHA. Re-run checks invalidated by preparation edits. Do not run several complete backend suites concurrently.

| Area | Directory | Command or required evidence |
| --- | --- | --- |
| SDK | `packages/umbod-sdk` | `uv run --locked pytest tests -q`; successful installed-wheel smoke job in Umbod CI |
| Backend | `umbod/api` | `uv run --locked pytest tests -q -n auto --maxprocesses=4 --dist=worksteal` |
| Backend lint | `umbod/api` | `uv run ruff check .` |
| Release/README contracts | `umbod/api` | `PYTHONPATH=.. uv run --locked pytest ../scripts/tests -q -n 0` |
| Frontend | `umbod/frontend` | `bun install --frozen-lockfile && bun run test && bun run check` |
| Documentation | `umbod` | `uv run --locked mkdocs build --strict` |
| Website and rendered docs | `website` | `bun install --frozen-lockfile && bun run test && bun run build` |
| Shared analysis | `umbod` | `uv run semgrep scan --config ../.semgrep.yml .`; apply repository remediation rules, never report findings as a clean scan |
| API/MCP changes | Repository root | `bash umbod/tests/kind-runtime/run.sh`; inspect failing assertions and pod diagnostics |
| Helm changes | Repository root | `umbod/deploy/helm/umbod/scripts/validate.sh` and `bash umbod/deploy/helm/umbod/scripts/kind-install-test.sh`; applicable negative schema checks |
| UI changes | `umbod` | Required Docker Compose setup and browser verification at `http://localhost:3010` from `AGENTS.md` |
| README changes | Repository root | All three source checks under `skills/development/write-module-readme/scripts/`, using that skill's requirements and the absolute repository root |

Run the complete unit/build checks above for release preparation. Runtime/Helm/UI/README additions apply to the changed area; explain any skip. CI evidence may satisfy a check only when the exact candidate and required job actually ran successfully. A green CI workflow with a path-filtered Kind skip does not establish runtime verification when runtime changes require it.

Inspect preview in a real browser after its Cloudflare build: home/Enterprise copy and install commands, documentation navigation, connector instructions, configuration defaults, compatibility/migration caveats, links and changed controls. Source metadata must use the approved version; compare root README and other hardcoded install commands separately. Current automation does not reconcile stale prose, including historical claims that Helm releases are independent of SDK/image releases.

For a local website smoke server, build first and run `bunx wrangler dev --port 8787` from `website/`. Tests exercise local Wrangler routes but do not themselves regenerate MkDocs or prove deployed documentation freshness. Do not use `bun run build:release` before tagging: it requires an exact release tag and fetches tags from origin.

## Pre-publication destination checks

Take versions only from `python3 umbod/scripts/release_versions.py --tag "$TAG"`. After updating source metadata, require `python3 umbod/scripts/release_versions.py --tag "$TAG" --metadata release-metadata.json` to succeed. Release preflight rejects mismatches before publication; ordinary production builds validate rather than silently stamp them. Preserve the distinct SDK/PyPI beta spelling. Confirm no existing local or remote tag has the selected name and no other `umbod-v*` tag points at the candidate commit.

Use the release workflow's `Ensure release versions are unpublished` step as the authoritative lookup contract:

- PyPI: query `https://pypi.org/pypi/umbod/${SDK_VERSION}/json`. HTTP 200 is a collision; confirmed HTTP 404 is absent; network failures and other statuses block release.
- GHCR images: enumerate all pages of `orgs/computerlovetech/packages/container/PACKAGE/versions?per_page=100` with `gh api --paginate`, inspecting every `metadata.container.tags` entry for the exact `IMAGE_VERSION`. Packages are `umbod`, `umbod-frontend` and `umbod-connector-builder`.
- GHCR chart: perform the same exact-tag check for package `charts%2Fumbod` against `CHART_VERSION`.
- Inspect error statuses instead of treating empty/error output as available. Confirm package access before interpreting a first-page package 404 as absence. Do not delete or overwrite a collision to make preflight pass.

Preflight checks are repeated after tag push. They are not an atomic reservation; avoid overlapping release runs.

## Published artifacts

Use `SDK_VERSION`, `IMAGE_VERSION` and `CHART_VERSION` recorded from the resolver, and the approved `RELEASE_SHA`.

| Artifact | Verification |
| --- | --- |
| PyPI SDK | Fetch `https://pypi.org/pypi/umbod/${SDK_VERSION}/json`; require expected version and wheel/sdist files. Install that exact distribution into a clean Python 3.14 environment; verify distribution `umbod` and import `umbod_sdk.connectors`. Distinguish this from the pre-release installed-wheel CI test. |
| Core image | `docker buildx imagetools inspect "ghcr.io/computerlovetech/umbod:${IMAGE_VERSION}"` |
| Frontend image | `docker buildx imagetools inspect "ghcr.io/computerlovetech/umbod-frontend:${IMAGE_VERSION}"` |
| Connector builder image | `docker buildx imagetools inspect "ghcr.io/computerlovetech/umbod-connector-builder:${IMAGE_VERSION}"` |
| Chart metadata | `helm show chart oci://ghcr.io/computerlovetech/charts/umbod --version "$CHART_VERSION"`; require version `CHART_VERSION` and appVersion `IMAGE_VERSION` |
| Chart defaults | `helm show values oci://ghcr.io/computerlovetech/charts/umbod --version "$CHART_VERSION"`; check core/frontend image tags |
| Published chart render | `helm template umbod oci://ghcr.io/computerlovetech/charts/umbod --version "$CHART_VERSION"`; require core/frontend image references with `IMAGE_VERSION` |

For every image, require both `linux/amd64` and `linux/arm64`, record the digest, and inspect platform image configuration for `org.opencontainers.image.revision=RELEASE_SHA`, `org.opencontainers.image.version=IMAGE_VERSION`, and `org.opencontainers.image.umbod.sdk.version=SDK_VERSION`. An image-index listing alone does not verify those labels or installed SDK compatibility. Inspect the release run's local core/builder installed-SDK checks as well.

A release publishes artifacts; it does not install or upgrade a user's Kubernetes cluster. Use the repository's disposable Kind checks for applicable runtime evidence and never silently substitute a production cluster or Docker Compose.

## Production branch and live website

1. Confirm GitHub rules restrict production updates to the authorized promotion identity with no human push bypass. The existing history-protection rule alone does not provide that guarantee; see `website/deployment.md` and stop if strict update enforcement is still missing.
2. Fetch production afresh. `git rev-parse origin/production` must equal `git rev-parse "${TAG}^{commit}"` for a new ordinary release. Stop if the branch is ahead or divergent; do not force it backward.
3. Inspect Cloudflare's separate production build and deployment: correct commit, successful deployment, Worker `umbod-website`, custom domain `umbod.ai`. A GitHub promotion success or a custom-domain attachment alone is insufficient. Record pending, failed or inaccessible Cloudflare evidence honestly, even if HTTP probes already work.
4. Check these paths on both `https://umbod.ai` and `https://preview.umbod.ai`: `/`, `/docs/`, `/enterprise`, `/enterprise/`, `/enterprise.html`, `/download`, `/download/`, and a new unknown path. Require successful real pages, Enterprise/legacy redirects to their documented destinations, working asset links, and a genuine 404 for the unknown path.
5. On production check home/Enterprise chart commands, `/docs/getting-started/kubernetes-installation/`, `/docs/plugins/build-a-connector/`, and `/docs/reference/helm-values/`. Installation commands must name the new chart/image/SDK versions where used. The Helm reference's source default-value table need not equal stamped release package defaults.
6. Use `agent_browser` for visible content and changed interactions; inspect console/page errors and failed requests. Test relevant desktop/mobile navigation, command copying, keyboard focus and JavaScript-disabled navigation when changed. Use actual observed conditions, not fixed sleeps, and distinguish stale DNS/cache from application failure.
7. Confirm preview's build corresponds to main and its domain remains on `umbod-website-preview`; its metadata comes from main, not the production release checkout. Production and preview can legitimately display the same version if main's committed metadata matches the release.

## Completion record

Record the approved tag and SHA, resolver outputs, reviewed docs/site changes and release notes, exact CI runs and skips, artifact digests/versions, production SHA, Cloudflare build/deployment result, live URL/version/route checks, and any remaining blocker. Do not claim artifact signing, security certification, application-cluster deployment or GitHub Release creation unless separately performed and verified.
