#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(python3 scripts/release.py version)"
OUTPUT="${UMBOD_DIST_DIR:-$PWD/dist}"
scripts/build.sh release
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/umbod-dmg.XXXXXX")"
trap 'rm -rf "$STAGING"' EXIT
ditto "$OUTPUT/Umbod-$VERSION.app" "$STAGING/Umbod.app"
ln -s /Applications "$STAGING/Applications"
cp "$OUTPUT/SIGNING.txt" "$STAGING/SIGNING.txt"
cp README.md "$STAGING/README.txt"
hdiutil create -volname "Umbod Desktop" -srcfolder "$STAGING" -ov -format UDZO "$OUTPUT/Umbod-$VERSION-arm64.dmg"
shasum -a 256 "$OUTPUT/Umbod-$VERSION-arm64.dmg" > "$OUTPUT/SHA256SUMS"
