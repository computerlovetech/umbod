---
name: release-umbod
description: >-
  Manually prepare and release Umbod: review product changes, documentation and
  website content, align release versions, verify the exact main commit, publish
  the approved release tag, and verify artifacts and Cloudflare production.
disable-model-invocation: true
---

# Release Umbod

## Scope and safety

- Run only when explicitly invoked. Creating or installing this skill does not authorize a release.
- Ask for the intended stable or beta version if unspecified. Never guess the next version or reuse an existing release tag.
- Prepare and verify first; obtain explicit approval of the final tag and commit before pushing the tag unless the user has already authorized that exact pair.
- A tag push publishes the SDK, three images and Helm chart, then promotes the production website. This is not transactional. Do not run concurrent releases.
- Never force-push production, move/delete release tags, overwrite published artifacts, run retention deletion, or deploy directly with `bun run deploy` as an ordinary release step.

All repository paths and command working directories below are relative to the repository root. Locate it with `git rev-parse --show-toplevel`; do not use the installed skill directory as the repository root. Bundled references are relative to this skill directory.

## 1. Establish current truth

1. Read `AGENTS.md`, `.github/workflows/umbod-release.yml`, `.github/workflows/umbod-ci.yml`, `.github/workflows/website-ci.yml`, `umbod/scripts/release_versions.py`, `website/scripts/prepare-release.sh`, and `website/deployment.md`. Recheck executable behavior on every invocation rather than trusting a previous release report.
2. Check the working tree and Git remotes. Preserve unrelated staged, unstaged and untracked work; never auto-stash, discard, or include it in release commits. Verify publication targets `computerlovetech/umbod`, not a fork.
3. Fetch main and release tags from origin; fetch production if it exists. Inspect the latest successful release run, published versions, and changes since that release. Do not equate the highest tag with a completed release.
4. Confirm GitHub authentication, Git tag-push permission, GHCR publication access, the `umbod-pypi` environment allowing `umbod-v*` tags, and its PyPI trusted publisher. Confirm the promotion job's authenticated identity can write production under the active branch rules. Require workflow-only update enforcement, not just a project convention: a built-in Actions token is not a valid restricted-actor bypass in this repository. If the dedicated promotion identity and credential controls are not configured, stop and report the missing protection; do not bypass it with a personal push. No Cloudflare secret is needed.
5. Confirm Cloudflare's preview app watches main and production app watches production with the build/deploy settings in `website/deployment.md`. Production must not have website-only watch-path filters or deployments from other branches. If console state cannot be inspected, report it as unverified and request confirmation.

## 2. Prepare content and versions

1. Review the release diff for features, fixes, breaking changes, configuration/migration needs, authentication/security changes, connector compatibility, and known limitations. Compare documented claims with implemented and tested behavior.
2. Update relevant `umbod/docs/` guides, navigation in `umbod/mkdocs.yml`, root `README.md`, SDK/chart documentation, and affected module READMEs. Use `write-module-readme` for module indexes. Search for hardcoded installation versions and obsolete release instructions; do not perform a repository-wide numeric replacement.
3. Review `website/index.html`, `website/enterprise/index.html`, shared content, and documentation links. Ensure promotion, onboarding commands, capabilities and limitations describe the release; do not promise unavailable features. Draft concise user-facing release notes.
4. Set `TAG` to the user-approved canonical tag. Run `python3 umbod/scripts/release_versions.py --tag "$TAG"` and record its `sdk_version`, `image_version`, and `chart_version` outputs as `SDK_VERSION`, `IMAGE_VERSION`, and `CHART_VERSION` respectively. Only `umbod-vMAJOR.MINOR.PATCH` and `umbod-vMAJOR.MINOR.PATCH-beta.N` are supported; beta SDK spelling is `MAJOR.MINOR.PATCHbN`.
5. Update root `release-metadata.json`: `chartVersion` from `chart_version`, `imageTag` from `image_version`, and `sdkVersion` from `sdk_version`. Run `python3 umbod/scripts/release_versions.py --tag "$TAG" --metadata release-metadata.json` and require success. This same check runs before artifact publication and in ordinary production builds. Check hardcoded README installation commands separately; website stamping does not update them.
6. Do not mechanically bump SDK manifests/locks, chart version/appVersion, or image defaults. The release workflow stamps isolated SDK, image and chart build copies. Ordinary production builds validate committed metadata without rewriting it; only the legacy bootstrap stamps locally. Generated Helm reference default values describe source configuration, not necessarily the published release's defaults.
7. Do not commit generated `website/dist/` or `website/public/docs/`. Review any regenerated `umbod/docs/reference/helm-values.md` against the actual chart; do not mistake a build side effect for an intended source change. Do not copy the legacy production bootstrap tag marker onto main.

## 3. Verify and freeze the candidate

1. Run the applicable checks in [verification.md](references/verification.md). Before tagging, website validation uses `bun run build`, not `build:release`: an untagged candidate must not be given a temporary release tag merely to make a check pass. Inspect preview, rendered installation versions and documentation content as well as test results.
2. Commit only approved preparation changes and get them onto main through the repository's normal process. Push main before tagging. Require a clean candidate checkout; use a separate worktree when other work must remain untouched.
3. Record the immutable candidate as `RELEASE_SHA`. Require `git merge-base --is-ancestor "$RELEASE_SHA" origin/main` to succeed. If production exists, require `git merge-base --is-ancestor origin/production "$RELEASE_SHA"` to succeed, so promotion can fast-forward. Stop on divergence; do not repeat the historical bootstrap or force a branch update.
4. Require `git tag --points-at "$RELEASE_SHA" --list 'umbod-v*'` to return no release tag. A stable release and its beta must use different commits. Check both local and remote names for the proposed tag; stop on any collision.
5. Find the exact main-push Umbod CI run with `gh run list --repo computerlovetech/umbod --workflow umbod-ci.yml --branch main --event push --commit "$RELEASE_SHA"`. Wait for the entire run with `gh run watch RUN_ID --repo computerlovetech/umbod --exit-status`, substituting its observed ID. Require conclusion success, not merely a green individual job, PR run, or Website CI run. Main image publication and nightly promotion occur after `ci-complete`.
6. Require the relevant Website CI run and preview build for that same commit to succeed. Check required Kind jobs explicitly; distinguish legitimately irrelevant skips from runtime verification that was required but never ran. Resolve failures or stop with the blocking evidence.
7. Perform the read-only collision checks used by the release workflow's `Ensure release versions are unpublished` step: exact SDK version on PyPI, exact image tag in all three GHCR packages, and exact chart version. Include all GHCR pages and tags. Only a confirmed absence is available; authentication, network and registry lookup errors are blockers. Workflow preflight repeats these checks but does not reserve versions.
8. Present the final release plan: tag, SHA, resolved versions, content/docs changes, test and runtime evidence, preview URL, production ancestry, destination availability, release notes, and outstanding risks. Obtain the required publication approval before continuing.

## 4. Publish exactly one tag

1. Re-fetch origin/main, production if present, and release tags; repeat ancestry and collision checks if state changed. Tag the approved SHA, not an implicit current HEAD. Do not silently change the approved candidate.
2. Create the annotated tag with `git tag -a "$TAG" "$RELEASE_SHA" -m "Umbod $TAG"` and verify `git rev-parse "${TAG}^{commit}"` equals the approved SHA.
3. Push only that tag with `git push origin "refs/tags/$TAG"`. Never use `git push --tags`. Tag pushes are the release trigger; creating a GitHub Release or calling workflow dispatch does not replace this step.
4. Locate the new `umbod-release.yml` run for this tag and SHA, record its URL, and watch it to completion. Expected order: provenance/version/collision plan → PyPI SDK → all three multiarchitecture images → Helm chart → website build/tests → production branch advancement. Complete any approved environment gate without weakening its policy.

## 5. Verify the actual release

1. Verify published artifacts using [verification.md](references/verification.md): SDK version and installed wheel, three images and both architectures, revision/SDK labels, and chart version/appVersion/rendered image references. Matching version strings alone do not prove runtime compatibility.
2. Freshly fetch production and require its SHA to equal the release tag's commit for an ordinary release. Do not treat the legacy deployment-only bootstrap as the normal release procedure.
3. Inspect the separate Cloudflare production build for that exact commit and Worker `umbod-website`. Require successful deployment; a successful GitHub promotion proves only a Git branch update.
4. Verify `https://umbod.ai` in a real browser: home and Enterprise installation commands use `chart_version`; installation guides use the release image/chart versions; `/docs/plugins/build-a-connector/` uses `sdk_version`; documentation links, assets, redirects and unknown-path 404s work. Check relevant responsive navigation, copying and keyboard behavior when changed. Investigate DNS/certificate or stale-cache failures rather than assuming the domain attachment proves availability.
5. Verify `https://preview.umbod.ai` remains attached to its own Worker and tracks main. Its committed versions may change with main; it must not be overwritten by the production deployment. Never deploy preview to the production Worker to fix a failed release.
6. Publish a GitHub Release entry or external announcement only if requested/approved, after artifacts and the live site are verified. The current workflow does not create a GitHub Release, sign artifacts, or deploy an Umbod application cluster automatically; do not claim it does.

## Recovery and completion

- On failure, stop and inspect the failing assertions/logs and what has already published. Never call a partial release successful or blindly rerun the entire workflow: preflight rejects published versions.
- Resume only the verified failed jobs in the original run when safe, retaining successful plan/SDK outputs. If an artifact was published before a job failed, reconcile it before retrying. If the run cannot safely resume, agree a fresh version after fixes; never reuse or move the old tag.
- If only website promotion failed, rerun that failed job. If promotion succeeded but Cloudflare failed, retry the Cloudflare build for the same production commit. Do not republish the SDK/images/chart for a website-only failure.
- For an emergency website rollback, obtain authorization and select an earlier deployment in Cloudflare; do not rewind production or overwrite release artifacts.
- Report separately: tag/SHA and resolved versions; GitHub release-run URL and conclusion; artifact versions/digests; production SHA; Cloudflare build/deployment evidence; live production/preview checks; and any warnings, skips, failures or unverified steps. A release is complete only after all required checkpoints pass. If any remain pending, state exactly what remains and who must act.
