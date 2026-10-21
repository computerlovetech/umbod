#!/bin/bash
set -euo pipefail
# Bundle uv's relocatable CPython plus locked wheels. Build tools are never runtime prerequisites.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$1"
mkdir -p "$DEST"
# Pin both the interpreter version and build, not whichever uv has cached locally.
ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/umbod-python.XXXXXX")"
trap 'rm -f "$ARCHIVE"' EXIT
curl --fail --location --silent --show-error --retry 3 'https://github.com/astral-sh/python-build-standalone/releases/download/20260310/cpython-3.14.3%2B20260310-aarch64-apple-darwin-install_only_stripped.tar.gz' --output "$ARCHIVE"
printf '%s  %s\n' '1a98bbe7e63547d2f764bc9119f6d604dfb333f21afab5f4885dc362b4f3a921' "$ARCHIVE" | shasum -a 256 --check -
tar -xzf "$ARCHIVE" -C "$DEST"
printf '20260310\n' > "$DEST/python/BUILD"
uv export --quiet --project "$ROOT/desktop/python" --frozen --no-dev --no-editable --no-hashes --output-file "$DEST/requirements.txt"
# Select wheels for macOS 14 even when building on a newer OS.
# Fresh source builds must not reuse wheels compiled for the build host.
# Export covers the full lock; development tool.uv.sources must not restore editable installs.
(cd "$ROOT/desktop/python" && MACOSX_DEPLOYMENT_TARGET=14.0 uv pip install --no-cache --python-platform aarch64-apple-darwin --python "$DEST/python/bin/python3" --reinstall-package umbod-desktop --reinstall-package umbod-core --reinstall-package umbod --break-system-packages --no-sources --requirements "$DEST/requirements.txt")
rm "$DEST/requirements.txt"
"$DEST/python/bin/python3" -I -B "$ROOT/desktop/scripts/verify-python-bundle.py"
"$DEST/python/bin/python3" -I -B "$ROOT/desktop/scripts/dependency-notices.py" python "$DEST"
# Compile before signing; runtime must not mutate the signed bundle.
"$DEST/python/bin/python3" -m compileall -q -s "$DEST/python" -p /umbod-runtime "$DEST/python/lib"
