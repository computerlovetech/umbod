#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:?test kit output directory required}"
bash scripts/check-macos-toolchain.sh
mkdir -p "$DEST/scripts" "$DEST/tests/fixtures"
/usr/bin/xcrun --toolchain XcodeDefault --sdk macosx swift build --package-path native --product UmbodTests
cp native/.build/debug/UmbodTests "$DEST/UmbodTests"
cp scripts/{accept-macos-artifact.sh,audit-macos-bundle.py,verify-python-bundle.py,fixture_stdio.py} "$DEST/scripts/"
cp tests/fixtures/update-manifest.json "$DEST/tests/fixtures/"
