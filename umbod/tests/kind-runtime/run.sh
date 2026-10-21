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
mcp_b_forward_pid=""
fixture_forward_pid=""
host_temporary_directory=""
api_port="${UMBOD_TEST_API_PORT:-28010}"
mcp_port="${UMBOD_TEST_MCP_PORT:-28011}"
export UMBOD_TEST_API_BASE_URL="http://127.0.0.1:${api_port}"
export UMBOD_TEST_MCP_URL="http://127.0.0.1:${mcp_port}/mcp"
export UMBOD_TEST_OTLP_BEARER_TOKEN="$(python3 -c 'import secrets; import sys; sys.stdout.write(secrets.token_urlsafe(32))')"
export UMBOD_TEST_ROOT_SECRET="$(python3 -c 'import secrets; import sys; sys.stdout.write(secrets.token_urlsafe(48))')"
export UMBOD_TEST_BEARER_TOKEN="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJraW5kLWNpIiwiaXNzIjoiaHR0cDovL2FnZW50LWNlbnRyYWwta2luZC5pbnZhbGlkIiwiZW1haWwiOiJraW5kLWNpQGV4YW1wbGUuaW52YWxpZCIsImdyb3VwcyI6WyJhZG1pbiJdfQ."

export UMBOD_TEST_BEARER_TOKEN_B="$(python3 -c 'import base64,json; encode=lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode(); print(encode({"alg":"none","typ":"JWT"})+"."+encode({"sub":"kind-ci-b","iss":"http://agent-central-kind.invalid","email":"kind-ci-b@example.invalid","groups":["admin"]})+".")')"
export UMBOD_TEST_KUBE_CONTEXT="${kube_context}"
export UMBOD_TEST_BOOTSTRAP_PATH="${script_directory}/bootstrap.py"
export UMBOD_TEST_MCP_B_URL="http://127.0.0.1:${UMBOD_TEST_MCP_B_PORT:-28013}/mcp"
export UMBOD_TEST_PERSONAL_URL="https://127.0.0.1:${UMBOD_TEST_PERSONAL_PORT:-28443}"

for command_name in docker helm kind kubectl curl uv openssl; do
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
    for forward_pid in "${api_forward_pid}" "${mcp_forward_pid}" "${mcp_b_forward_pid}" "${fixture_forward_pid}"; do
        if [[ -n "${forward_pid}" ]]; then
            kill "${forward_pid}" 2>/dev/null || true
            wait "${forward_pid}" 2>/dev/null || true
        fi
    done
    if [[ "${cluster_created}" == "true" ]]; then
        if [[ ${exit_status} -ne 0 ]]; then
            kubectl --context "${kube_context}" get pods,deployments,services -o wide || true
            kubectl --context "${kube_context}" describe pods || true
            kubectl --context "${kube_context}" logs --all-containers --prefix --tail=150 -l "app.kubernetes.io/instance=${release_name}" \
                | python3 "${script_directory}/check_secret_logs.py" --diagnostics || true
        fi
        if [[ "${UMBOD_TEST_KIND_KEEP_CLUSTER:-false}" != "true" ]]; then
            kind delete cluster --name "${cluster_name}" || true
        fi
    fi
    if [[ -n "${host_temporary_directory}" ]]; then
        rm -rf "${host_temporary_directory}"
    fi
    exit "${exit_status}"
}
trap finish EXIT
host_temporary_directory="$(mktemp -d)"
export UMBOD_TEST_PERSONAL_CA="${host_temporary_directory}/ca.crt"
export UMBOD_TEST_PERSONAL_PROXY_TOKENS="${host_temporary_directory}/proxy-tokens"

docker build --tag ghcr.io/computerlovetech/umbod:ci --file "${app_directory}/api/Dockerfile" "${repository_directory}"
docker build --tag ghcr.io/computerlovetech/umbod-frontend:ci "${app_directory}/frontend"
docker build --tag umbod-kind-test-connector:ci "${script_directory}/connector"

kind create cluster --name "${cluster_name}" --image "${UMBOD_KIND_NODE_IMAGE:-kindest/node:v1.32.2}" --wait 2m
cluster_created=true
kind load docker-image --name "${cluster_name}" ghcr.io/computerlovetech/umbod:ci ghcr.io/computerlovetech/umbod-frontend:ci umbod-kind-test-connector:ci

kubectl --context "${kube_context}" create secret generic umbod-ci \
    --from-literal="UMBOD_MCP_TEST_BEARER_TOKEN=${UMBOD_TEST_BEARER_TOKEN}" \
    --from-literal="UMBOD_MCP_TEST_BEARER_TOKEN_B=${UMBOD_TEST_BEARER_TOKEN_B}" \
    --from-literal="UMBOD_OTLP_BEARER_TOKEN=${UMBOD_TEST_OTLP_BEARER_TOKEN}" \
    --from-literal="UMBOD_ROOT_SECRET=${UMBOD_TEST_ROOT_SECRET}"
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
(cd "${app_directory}/api" && uv run --locked pytest live_runtime_tests --ignore=live_runtime_tests/test_running_personal_mcp_execution.py)
kubectl --context "${kube_context}" logs deployment/umbod-core --container api \
    | python3 "${script_directory}/check_telemetry_logs.py"
kubectl --context "${kube_context}" logs deployment/umbod-core --container mcp \
    | python3 "${script_directory}/check_secret_logs.py"

for forward_pid in "${api_forward_pid}" "${mcp_forward_pid}"; do
    kill "${forward_pid}" 2>/dev/null || true
    wait "${forward_pid}" 2>/dev/null || true
done
api_forward_pid=""
mcp_forward_pid=""
(cd "${app_directory}/api" && uv run --locked python "${script_directory}/setup_personal_runtime.py" "${host_temporary_directory}")
IFS= read -r UMBOD_TEST_BEARER_TOKEN < "${host_temporary_directory}/bearer-a"
IFS= read -r UMBOD_TEST_BEARER_TOKEN_B < "${host_temporary_directory}/bearer-b"
export UMBOD_TEST_BEARER_TOKEN UMBOD_TEST_BEARER_TOKEN_B
kubectl --context "${kube_context}" port-forward service/umbod-api "${api_port}:8000" --address 127.0.0.1 &
api_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp "${mcp_port}:8011" --address 127.0.0.1 &
mcp_forward_pid=$!
kubectl --context "${kube_context}" port-forward deployment/umbod-core "${UMBOD_TEST_MCP_B_PORT:-28013}:8013" --address 127.0.0.1 &
mcp_b_forward_pid=$!
kubectl --context "${kube_context}" port-forward deployment/personal-runtime "${UMBOD_TEST_PERSONAL_PORT:-28443}:8443" --address 127.0.0.1 &
fixture_forward_pid=$!
for attempt in $(seq 1 60); do
    if curl --fail --silent "${UMBOD_TEST_API_BASE_URL}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_MCP_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_MCP_B_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent --cacert "${UMBOD_TEST_PERSONAL_CA}" "${UMBOD_TEST_PERSONAL_URL}/health" >/dev/null; then
        break
    fi
    if [[ ${attempt} -eq 60 ]]; then
        printf '%s\n' 'Personal runtime port-forwards did not become healthy' >&2
        exit 1
    fi
    sleep 1
done
(cd "${app_directory}/api" && uv run --locked python -c '
import os
import runpy
from urllib.request import build_opener, install_opener
opener = build_opener()
opener.addheaders = [("Authorization", "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN"])]
install_opener(opener)
runpy.run_path(os.environ["UMBOD_TEST_BOOTSTRAP_PATH"], run_name="__main__")
')
(cd "${app_directory}/api" && uv run --locked pytest --tb=line live_runtime_tests/test_running_personal_mcp_execution.py)
for container_name in api mcp mcp-b; do
    kubectl --context "${kube_context}" logs deployment/umbod-core --container "${container_name}" \
        | python3 "${script_directory}/check_secret_logs.py"
done
