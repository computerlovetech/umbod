set -euo pipefail

repository="$(git rev-parse --show-toplevel)"
git -C "${repository}" fetch --prune origin 'refs/tags/umbod-v*:refs/tags/umbod-v*'
release_tag="$(git -C "${repository}" tag --points-at HEAD --list 'umbod-v*')"
[[ -n "${release_tag}" && "${release_tag}" != *$'\n'* ]] || { echo "Production builds require exactly one umbod-v release tag on HEAD" >&2; exit 1; }
versions="$(python3 "${repository}/umbod/scripts/release_versions.py" --tag "${release_tag}")"
python3 - "${repository}/release-metadata.json" "${versions}" <<'PY'
import json
import sys
from pathlib import Path

versions = dict(line.split("=", 1) for line in sys.argv[2].splitlines())
metadata = {
    "chartVersion": versions["chart_version"],
    "imageTag": versions["image_version"],
    "sdkVersion": versions["sdk_version"],
}
Path(sys.argv[1]).write_text(json.dumps(metadata, indent=2) + "\n")
PY
