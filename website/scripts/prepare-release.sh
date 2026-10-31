set -euo pipefail

repository="$(git rev-parse --show-toplevel)"
git -C "${repository}" fetch --prune origin 'refs/tags/umbod-v*:refs/tags/umbod-v*'
release_tag="$(git -C "${repository}" tag --points-at HEAD --list 'umbod-v*')"
bootstrap=false
if [[ -z "${release_tag}" && -f "${repository}/website/release-source.tag" ]]; then
  release_tag="$(< "${repository}/website/release-source.tag")"
  bootstrap=true
fi
[[ -n "${release_tag}" && "${release_tag}" != *$'\n'* ]] || { echo "Production builds require exactly one umbod-v release tag on HEAD" >&2; exit 1; }
if [[ "${bootstrap}" == false ]]; then
  python3 "${repository}/umbod/scripts/release_versions.py" --tag "${release_tag}" --metadata "${repository}/release-metadata.json" > /dev/null
  exit 0
fi
versions="$(python3 "${repository}/umbod/scripts/release_versions.py" --tag "${release_tag}")"
if [[ "${bootstrap}" == true ]]; then
  release_commit="$(git -C "${repository}" rev-parse --verify "refs/tags/${release_tag}^{commit}")"
  parents="$(git -C "${repository}" cat-file -p HEAD | awk '/^$/ { exit } $1 == "parent" { print $2 }')"
  [[ "${parents}" == "${release_commit}" ]] || { echo "Production bootstrap must directly follow its release commit" >&2; exit 1; }
  changed_paths="$(git -C "${repository}" diff --no-renames --name-only "${release_commit}" HEAD)"
  while IFS= read -r changed_path; do
    case "${changed_path}" in
      website/package.json|website/wrangler.jsonc|website/scripts/prepare-release.sh|website/release-source.tag) ;;
      *) echo "Production bootstrap must not change released content: ${changed_path}" >&2; exit 1 ;;
    esac
  done <<< "${changed_paths}"
fi
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
