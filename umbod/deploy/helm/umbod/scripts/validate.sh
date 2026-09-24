#!/usr/bin/env bash

set -euo pipefail

chart_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_directory="$(mktemp -d)"
rendered_chart="${workspace_directory}/rendered.yaml"
plugin_free_chart="${workspace_directory}/plugin-free.yaml"
invalid_plugin_values="${workspace_directory}/invalid-plugin-values.yaml"
invalid_plugin_tag_values="${workspace_directory}/invalid-plugin-tag-values.yaml"
invalid_available_without_image_values="${workspace_directory}/invalid-available-without-image-values.yaml"
invalid_blank_connector_values="${workspace_directory}/invalid-blank-connector-values.yaml"
invalid_duplicate_connector_values="${workspace_directory}/invalid-duplicate-connector-values.yaml"
plugin_image_empty_availability_values="${workspace_directory}/plugin-image-empty-availability-values.yaml"

cleanup() {
  rm -rf "${workspace_directory}"
}

trap cleanup EXIT

helm lint --strict "${chart_directory}" -f "${chart_directory}/ci/ci-values.yaml"
helm template umbod "${chart_directory}" -f "${chart_directory}/ci/ci-values.yaml" > "${rendered_chart}"
kubeconform -strict -summary "${rendered_chart}"
python3 "${chart_directory}/scripts/validate-rendered.py" "${rendered_chart}"
helm template umbod "${chart_directory}" > "${plugin_free_chart}"
if grep -q "connector-plugins" "${plugin_free_chart}"; then
  echo "plugin resources must not render without a plugin image" >&2
  exit 1
fi
if grep -q "kind: PersistentVolumeClaim" "${plugin_free_chart}"; then
  echo "default standalone configuration must not render a PVC" >&2
  exit 1
fi
if ! grep -q "emptyDir: {}" "${plugin_free_chart}"; then
  echo "default standalone configuration must use ephemeral storage" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  image:' '    repository: example.invalid/plugins' > "${invalid_plugin_values}"
if helm lint --strict "${chart_directory}" -f "${invalid_plugin_values}" >/dev/null 2>&1; then
  echo "plugin repository without a tag must fail schema validation" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  image:' '    tag: invalid' > "${invalid_plugin_tag_values}"
if helm lint --strict "${chart_directory}" -f "${invalid_plugin_tag_values}" >/dev/null 2>&1; then
  echo "plugin tag without a repository must fail schema validation" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  availableConnectorIds: [test]' > "${invalid_available_without_image_values}"
if helm lint --strict "${chart_directory}" -f "${invalid_available_without_image_values}" >/dev/null 2>&1; then
  echo "available connector IDs without a complete plugin image must fail schema validation" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  availableConnectorIds: [" "]' > "${invalid_blank_connector_values}"
if helm lint --strict "${chart_directory}" -f "${invalid_blank_connector_values}" >/dev/null 2>&1; then
  echo "blank available connector IDs must fail schema validation" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  availableConnectorIds: [test, test]' > "${invalid_duplicate_connector_values}"
if helm lint --strict "${chart_directory}" -f "${invalid_duplicate_connector_values}" >/dev/null 2>&1; then
  echo "duplicate available connector IDs must fail schema validation" >&2
  exit 1
fi
printf '%s\n' 'plugins:' '  availableConnectorIds: []' '  image:' '    repository: example.invalid/plugins' '    tag: immutable' > "${plugin_image_empty_availability_values}"
helm lint --strict "${chart_directory}" -f "${plugin_image_empty_availability_values}" >/dev/null
helm package "${chart_directory}" --destination "${workspace_directory}"
