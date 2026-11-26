#!/usr/bin/env bash
set -e

app_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scan_arguments=(
  --config ../.semgrep.yml
  --config ../.semgrep/production-design.yml
  --config ../.semgrep/test-correctness.yml
  --no-rewrite-rule-ids --error --metrics=off
)
targets=()

for argument in "$@"; do
  case "$argument" in
    --json) scan_arguments+=(--json) ;;
    -h|--help)
      printf 'Usage: %s [--json] [PATH ...]\n' "$0"
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

if [[ ${#targets[@]} -eq 0 ]]; then
  targets=(.)
fi

cd -- "$app_directory"
exec uv run --locked --only-group dev semgrep scan "${scan_arguments[@]}" "${targets[@]}"
