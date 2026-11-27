#!/usr/bin/env bash
set -e

app_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scan_arguments=(--no-rewrite-rule-ids --metrics=off)
frontend_advisory=false
targets=()

for argument in "$@"; do
  case "$argument" in
    --json) scan_arguments+=(--json) ;;
    --frontend-advisory) frontend_advisory=true ;;
    -h|--help)
      printf 'Usage: %s [--json] [--frontend-advisory] [PATH ...]\n' "$0"
      printf '  --frontend-advisory  Scan only advisory frontend rules without failing on findings.\n'
      exit 0
      ;;
    -*)
      printf 'Unknown option: %s\n' "$argument" >&2
      exit 2
      ;;
    /*) targets+=("$argument") ;;
    *) targets+=("$PWD/$argument") ;;
  esac
done

if [[ "$frontend_advisory" == true ]]; then
  scan_arguments+=(--config ../.semgrep/frontend-advisory.yml)
  default_target=frontend/src
else
  scan_arguments+=(
    --config ../.semgrep.yml
    --config ../.semgrep/production-design.yml
    --config ../.semgrep/test-correctness.yml
    --error
  )
  default_target=.
fi

if [[ ${#targets[@]} -eq 0 ]]; then
  targets=("$default_target")
fi

cd -- "$app_directory"
exec uv run --locked --only-group dev semgrep scan "${scan_arguments[@]}" "${targets[@]}"
