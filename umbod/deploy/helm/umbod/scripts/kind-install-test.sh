#!/usr/bin/env bash

set -Eeuo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_directory="$(cd "${script_directory}/../../../.." && pwd)"
repository_directory="$(cd "${app_directory}/.." && pwd)"
chart_directory="${app_directory}/deploy/helm/umbod"
cluster_name="${UMBOD_KIND_CLUSTER_NAME:-umbod-ci}"
node_image="${UMBOD_KIND_NODE_IMAGE:-kindest/node:v1.32.2}"
release_name="${UMBOD_HELM_RELEASE_NAME:-umbod}"
core_image="ghcr.io/computerlovetech/umbod:ci"
frontend_image="ghcr.io/computerlovetech/umbod-frontend:ci"
core_image_archive=""
frontend_image_archive=""
cluster_created=false
kube_context="kind-${cluster_name}"

usage() {
    printf '%s\n' "Usage: $0 [--core-image-archive PATH --frontend-image-archive PATH]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --core-image-archive)
            core_image_archive="${2:?Missing core image archive path}"
            shift 2
            ;;
        --frontend-image-archive)
            frontend_image_archive="${2:?Missing frontend image archive path}"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

archive_count=0
for image_archive in "${core_image_archive}" "${frontend_image_archive}"; do
    if [[ -n "${image_archive}" ]]; then
        archive_count=$((archive_count + 1))
    fi
done
if [[ ${archive_count} -ne 0 && ${archive_count} -ne 2 ]]; then
    printf '%s\n' "Both image archives must be supplied together." >&2
    exit 2
fi

for command_name in docker helm kind kubectl; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        printf '%s\n' "Required command not found: ${command_name}" >&2
        exit 1
    fi
done

docker info >/dev/null

if kind get clusters | grep -Fxq "${cluster_name}"; then
    printf '%s\n' "Kind cluster already exists: ${cluster_name}" >&2
    exit 1
fi

collect_diagnostics() {
    helm --kube-context "${kube_context}" status "${release_name}" || true
    kubectl --context "${kube_context}" get pods,deployments,services,persistentvolumeclaims -o wide || true
    kubectl --context "${kube_context}" get events --sort-by=.lastTimestamp || true
    kubectl --context "${kube_context}" describe pods || true
    kubectl --context "${kube_context}" logs --all-containers --prefix --tail=-1 -l "app.kubernetes.io/instance=${release_name}" || true
}

finish() {
    exit_status=$?
    if [[ "${cluster_created}" == "true" && ${exit_status} -ne 0 ]]; then
        collect_diagnostics
    fi
    if [[ "${cluster_created}" == "true" && "${UMBOD_KIND_KEEP_CLUSTER:-false}" != "true" ]]; then
        kind delete cluster --name "${cluster_name}" || true
    fi
    exit "${exit_status}"
}

trap finish EXIT

if [[ -n "${core_image_archive}" ]]; then
    docker load --input "${core_image_archive}"
    docker load --input "${frontend_image_archive}"
else
    docker build --tag "${core_image}" --file "${app_directory}/api/Dockerfile" "${repository_directory}"
    docker build --tag "${frontend_image}" "${app_directory}/frontend"
fi

kind create cluster --name "${cluster_name}" --image "${node_image}" --wait 2m
cluster_created=true
kind load docker-image --name "${cluster_name}" "${core_image}" "${frontend_image}"

kubectl --context "${kube_context}" create secret generic umbod-ci \
    --from-literal=UMBOD_MCP_TEST_BEARER_TOKEN=eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJraW5kLWNpIiwiaXNzIjoiaHR0cDovL2FnZW50LWNlbnRyYWwta2luZC5pbnZhbGlkIiwiZW1haWwiOiJraW5kLWNpQGV4YW1wbGUuaW52YWxpZCIsImdyb3VwcyI6WyJhZG1pbiJdfQ.

helm --kube-context "${kube_context}" install "${release_name}" "${chart_directory}" \
    --values "${chart_directory}/ci/kind-values.yaml" \
    --wait \
    --timeout 5m

helm --kube-context "${kube_context}" test "${release_name}" --logs --timeout 2m
