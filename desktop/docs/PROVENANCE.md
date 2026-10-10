# Desktop import provenance and audit

Source: `kasperjunge/umbod-desktop`, exact commit `866dc2f7d0339bd52598a9be7d68570864552b1e`. The source checkout was read-only. Tracked files were extracted with `git archive` at that commit; no working-tree files, git history, existing binaries, or source build outputs were copied. `import-sha256.json` records the exact original bytes for every imported file, before the monorepo adjustments described below.

## Allowlist

Imported Cargo.toml, Cargo.lock, backend source/tests, Swift package/source/tests, Windows project/source/tests, .gitignore, and these scripts: build.sh, build-windows.ps1, package.sh, package-windows.ps1, package-windows.py, test_windows_package.py, icon.swift, ui-smoke.sh, verify.sh, fixture_stdio.py, fixture_issues.py, native-smoke.py, activation-e2e.py, oauth-bundle-e2e.py.

Excluded the source README and BUILD_BRIEF, all source docs and evidence, the upstream workflow, connection-headers.py and its tests, all personal configuration, git metadata/history, generated binaries/archives, cache directories and untracked files. Source docs contained private operational history and were not appropriate public import material. Documentation here is newly written for the monorepo.

## Review

Scanned every allowlisted text file for private absolute paths, email addresses, token/key patterns, PEM private keys, upstream identity references, licensing/copyright strings, and embedded URLs. No live secret or personal email was identified in the allowlist. The single `/Users/not-real` path is an intentional synthetic Swift test fixture. UUIDs and fixture tokens in tests are test inputs; app bundle/vault IDs are required product identifiers, not personal account IDs. The former project button pointed to the upstream owner; it now points to `computerlovetech/umbod`. Public provider documentation and localhost fixture URLs remain. Build/runtime source can access vault credentials as a product feature; no stored credentials were imported.

This is a bounded import audit, not a security certification. Dependency vulnerabilities, platform trust, and end-to-end real provider behavior require their normal review before release.

## Owner-authorized public import and dependency notices

The source owner explicitly authorized this public import. Ownership/permission for the imported source is therefore confirmed for this import, not an unresolved source grant. The audited source commit has no tracked LICENSE file; the owner's authorization is the basis for the public import, rather than an inferred upstream license. This authorization does not establish third-party dependency rights or notice completeness, and the monorepo root MIT license does not replace applicable dependency licenses/notices. The manual release still requires explicit rights confirmation; production releases are disabled regardless of that confirmation. Do not treat the checkbox alone as a legal review.

Cargo.lock pins Rust dependencies; Cargo metadata exposes their declared licenses. The macOS-filtered offline dependency audit resolved 222 third-party crates, all with declared license expressions (including multi-license and notice obligations). This metadata inspection does not certify notice completeness or redistribution compliance; other targets must be reviewed too. Swift uses Apple system frameworks and has no package dependencies. The WPF application depends on .NET/WindowsDesktop runtime components in self-contained packages; preserve their bundled license and third-party notices. Review the actual packaged contents and generate any missing Rust dependency notices before publication. Dependency license clearance and notice completeness remain publication blockers, not claimed completed work.

## Monorepo changes

New desktop version policy, native CI, explicit release guard and manifest generation; replaced version literals in packaging/app metadata with VERSION; removed automatic signing-identity discovery; changed project link; rewrote documentation and historical verification claims. Build scripts resolve their own desktop directory, so root invocation works. The root Docker context excludes desktop. The original Kubernetes workflows and root release metadata are byte-preserved and covered by baseline hash tests.

Historical source Windows evidence: https://github.com/kasperjunge/umbod-desktop/actions/runs/37907078176. No new target CI run is implied.
