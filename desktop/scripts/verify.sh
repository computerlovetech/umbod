#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/check-macos-toolchain.sh
(cd python && uv run --locked ruff check . && uv run --locked pytest -q)
bash scripts/build.sh dev
/usr/bin/xcrun --toolchain XcodeDefault --sdk macosx swift run --package-path native UmbodTests
