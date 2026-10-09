#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.cargo/bin:$PATH"
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
swift build --package-path native
swift run --package-path native UmbodTests
