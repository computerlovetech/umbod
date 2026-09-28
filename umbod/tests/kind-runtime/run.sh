#!/usr/bin/env bash

set -Eeuo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_directory="$(cd "${script_directory}/../.." && pwd)"
repository_directory="$(cd "${app_directory}/.." && pwd)"
chart_directory="${app_directory}/deploy/helm/umbod"
cluster_name="${UMBOD_TEST_KIND_CLUSTER_NAME:-umbod-runtime-tests}"
kube_context="kind-${cluster_name}"
release_name="umbod"
cluster_created=false
api_forward_pid=""
mcp_forward_pid=""
api_port="${UMBOD_TEST_API_PORT:-28010}"
mcp_port="${UMBOD_TEST_MCP_PORT:-28011}"
export UMBOD_TEST_API_BASE_URL="http://127.0.0.1:${api_port}"
export UMBOD_TEST_MCP_URL="http://127.0.0.1:${mcp_port}/mcp"
export UMBOD_TEST_BEARER_TOKEN="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJraW5kLWNpIiwiaXNzIjoiaHR0cDovL2FnZW50LWNlbnRyYWwta2luZC5pbnZhbGlkIiwiZW1haWwiOiJraW5kLWNpQGV4YW1wbGUuaW52YWxpZCIsImdyb3VwcyI6WyJhZG1pbiJdfQ."

for command_name in docker helm kind kubectl curl uv; do
    command -v "${command_name}" >/dev/null
 done

docker info >/dev/null
if kind get clusters | grep -Fxq "${cluster_name}"; then
    printf 'Kind cluster already exists: %s\n' "${cluster_name}" >&2
    exit 1
fi

finish() {
    exit_status=$?
    trap - EXIT
    for forward_pid in "${api_forward_pid}" "${mcp_forward_pid}"; do
        if [[ -n "${forward_pid}" ]]; then
            kill "${forward_pid}" 2>/dev/null || true
            wait "${forward_pid}" 2>/dev/null || true
        fi
    done
    if [[ "${cluster_created}" == "true" ]]; then
        if [[ ${exit_status} -ne 0 ]]; then
            kubectl --context "${kube_context}" get pods,deployments,services -o wide || true
            kubectl --context "${kube_context}" describe pods || true
            kubectl --context "${kube_context}" logs --all-containers --prefix --tail=150 -l "app.kubernetes.io/instance=${release_name}" || true
        fi
        if [[ "${UMBOD_TEST_KIND_KEEP_CLUSTER:-false}" != "true" ]]; then
            kind delete cluster --name "${cluster_name}" || true
        fi
    fi
    exit "${exit_status}"
}
trap finish EXIT

docker build --tag ghcr.io/computerlovetech/umbod:ci --file "${app_directory}/api/Dockerfile" "${repository_directory}"
docker build --tag ghcr.io/computerlovetech/umbod-frontend:ci "${app_directory}/frontend"
docker build --tag umbod-kind-test-connector:ci "${script_directory}/connector"

kind create cluster --name "${cluster_name}" --image "${UMBOD_KIND_NODE_IMAGE:-kindest/node:v1.32.2}" --wait 2m
cluster_created=true
kind load docker-image --name "${cluster_name}" ghcr.io/computerlovetech/umbod:ci ghcr.io/computerlovetech/umbod-frontend:ci umbod-kind-test-connector:ci

kubectl --context "${kube_context}" create secret generic umbod-ci --from-literal="UMBOD_MCP_TEST_BEARER_TOKEN=${UMBOD_TEST_BEARER_TOKEN}"
helm --kube-context "${kube_context}" install "${release_name}" "${chart_directory}" \
    --values "${chart_directory}/ci/kind-values.yaml" \
    --values "${script_directory}/values.yaml" \
    --wait --timeout 5m
helm --kube-context "${kube_context}" test "${release_name}" --logs --timeout 2m

kubectl --context "${kube_context}" set env deployment/umbod-core --containers=mcp \
    UMBOD_MCP_TOOL_EXPOSURE=flat UMBOD_MCP_STATELESS_HTTP=false UMBOD_MCP_PERMISSION_CLAIM=groups
kubectl --context "${kube_context}" rollout status deployment/umbod-core --timeout=3m

kubectl --context "${kube_context}" port-forward service/umbod-api "${api_port}:8000" --address 127.0.0.1 &
api_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp "${mcp_port}:8011" --address 127.0.0.1 &
mcp_forward_pid=$!

for attempt in $(seq 1 30); do
    if curl --fail --silent "${UMBOD_TEST_API_BASE_URL}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_MCP_URL%/mcp}/system/health" >/dev/null; then
        break
    fi
    if [[ ${attempt} -eq 30 ]]; then
        printf '%s\n' 'Kind runtime port-forwards did not become healthy' >&2
        exit 1
    fi
    sleep 1
done

python3 "${script_directory}/bootstrap.py"
(cd "${app_directory}/api" && uv run --locked pytest live_runtime_tests)
