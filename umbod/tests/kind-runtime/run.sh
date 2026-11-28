#!/usr/bin/env bash

set -Eeuo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_directory="$(cd "${script_directory}/../.." && pwd)"
repository_directory="$(cd "${app_directory}/.." && pwd)"
chart_directory="${app_directory}/deploy/helm/umbod"
cluster_name="${UMBOD_TEST_KIND_CLUSTER_NAME:-}"
release_name="umbod"
cluster_created=false
export UMBOD_TEST_FILESYSTEM_PREVIEW_MAX_BYTES="${UMBOD_TEST_FILESYSTEM_PREVIEW_MAX_BYTES:-2097152}"
export UMBOD_TEST_CONTENT_BACKEND="${UMBOD_TEST_CONTENT_BACKEND:-local}"
if [[ "${UMBOD_TEST_CONTENT_BACKEND}" != "local" && "${UMBOD_TEST_CONTENT_BACKEND}" != "s3" ]]; then
    printf '%s\n' 'UMBOD_TEST_CONTENT_BACKEND must be local or s3' >&2
    exit 1
fi
if [[ "${UMBOD_TEST_CONTENT_BACKEND}" == "s3" ]]; then
    export UMBOD_TEST_AWS_ACCESS_KEY_ID="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    export UMBOD_TEST_AWS_SECRET_ACCESS_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
api_b_forward_pid=""
api_forward_pid=""
otlp_forward_pid=""
mcp_forward_pid=""
admin_mcp_forward_pid=""
mcp_b_forward_pid=""
fixture_forward_pid=""
host_temporary_directory=""
api_port="${UMBOD_TEST_API_PORT:-28010}"
mcp_port="${UMBOD_TEST_MCP_PORT:-28011}"
admin_mcp_port="${UMBOD_TEST_ADMIN_MCP_PORT:-28017}"
export UMBOD_TEST_ADMIN_MCP_URL="http://127.0.0.1:${admin_mcp_port}/mcp"
otlp_port="${UMBOD_TEST_OTLP_PORT:-24318}"
export UMBOD_TEST_OTLP_BASE_URL="http://127.0.0.1:${otlp_port}"
export UMBOD_TEST_API_BASE_URL="http://127.0.0.1:${api_port}"
export UMBOD_TEST_MCP_URL="http://127.0.0.1:${mcp_port}/mcp"
export UMBOD_TEST_OTLP_BEARER_TOKEN="$(python3 -c 'import secrets; import sys; sys.stdout.write(secrets.token_urlsafe(32))')"
export UMBOD_TEST_ROOT_SECRET="$(python3 -c 'import secrets; import sys; sys.stdout.write(secrets.token_urlsafe(48))')"
export UMBOD_TEST_BEARER_TOKEN="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJraW5kLWNpIiwiZW1haWwiOiJraW5kLWNpQGV4YW1wbGUuaW52YWxpZCIsImdyb3VwcyI6WyJhZG1pbiJdfQ."

export UMBOD_TEST_BEARER_TOKEN_B="$(python3 -c 'import base64,json; encode=lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode(); print(encode({"alg":"none","typ":"JWT"})+"."+encode({"sub":"kind-ci-b","email":"kind-ci-b@example.invalid","groups":["admin"]})+".")')"
export UMBOD_TEST_BOOTSTRAP_PATH="${script_directory}/bootstrap.py"
export UMBOD_TEST_API_B_BASE_URL="http://127.0.0.1:${UMBOD_TEST_API_B_PORT:-28015}"
export UMBOD_TEST_MCP_B_URL="http://127.0.0.1:${UMBOD_TEST_MCP_B_PORT:-28013}/mcp"
export UMBOD_TEST_PERSONAL_URL="https://127.0.0.1:${UMBOD_TEST_PERSONAL_PORT:-28443}"

for command_name in docker helm kind kubectl curl uv openssl python3; do
    command -v "${command_name}" >/dev/null
done

lock_directory="${HOME}/.cache/umbod"
mkdir -p "${lock_directory}"
exec 9>>"${lock_directory}/kind-runtime.lock"
python3 -c '
import fcntl
import sys

try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit("Another Umbod Kind runtime run is active. Wait for it to finish before retrying; host ports and image tags are shared.")
'

docker info >/dev/null
cluster_name="${cluster_name:-umbod-runtime-tests-$(openssl rand -hex 6)}"
kube_context="kind-${cluster_name}"
export UMBOD_TEST_KUBE_CONTEXT="${kube_context}"
existing_clusters="$(kind get clusters)"
if grep -Fxq -- "${cluster_name}" <<< "${existing_clusters}"; then
    printf 'Kind cluster already exists: %s. Choose a different UMBOD_TEST_KIND_CLUSTER_NAME.\n' "${cluster_name}" >&2
    exit 1
fi
printf 'Kind runtime cluster: %s\n' "${cluster_name}"

finish() {
    exit_status=$?
    trap - EXIT
    for forward_pid in "${api_forward_pid}" "${otlp_forward_pid}" "${api_b_forward_pid}" "${mcp_forward_pid}" "${mcp_b_forward_pid}" "${admin_mcp_forward_pid}" "${fixture_forward_pid}"; do
        if [[ -n "${forward_pid}" ]]; then
            kill "${forward_pid}" 2>/dev/null || true
            wait "${forward_pid}" 2>/dev/null || true
        fi
    done
    if [[ "${cluster_created}" == "true" ]]; then
        if [[ ${exit_status} -ne 0 ]]; then
            kubectl --context "${kube_context}" get pods,deployments,services -o wide || true
            kubectl --context "${kube_context}" describe pods \
                | python3 "${script_directory}/check_secret_logs.py" --diagnostics || true
            kubectl --context "${kube_context}" logs --all-containers --prefix --tail=150 -l "app.kubernetes.io/instance=${release_name}" \
                | python3 "${script_directory}/check_secret_logs.py" --diagnostics || true
        fi
        if [[ "${UMBOD_TEST_KIND_KEEP_CLUSTER:-false}" != "true" ]]; then
            if ! kind delete cluster --name "${cluster_name}"; then
                printf 'Failed to clean up Kind cluster: %s\n' "${cluster_name}" >&2
                if [[ ${exit_status} -eq 0 ]]; then
                    exit_status=1
                fi
            fi
        else
            printf 'Retained Kind cluster: %s. Use kind export kubeconfig --name %s to access it.\n' "${cluster_name}" "${cluster_name}"
        fi
    fi
    if [[ -n "${host_temporary_directory}" ]]; then
        rm -rf "${host_temporary_directory}"
    fi
    exit "${exit_status}"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
host_temporary_directory="$(mktemp -d)"
export KUBECONFIG="${host_temporary_directory}/kubeconfig"
export UMBOD_TEST_PERSONAL_CA="${host_temporary_directory}/ca.crt"
export UMBOD_TEST_PERSONAL_PROXY_TOKENS="${host_temporary_directory}/proxy-tokens"

if [[ "${UMBOD_TEST_CONTENT_BACKEND}" == "s3" ]]; then
    export UMBOD_TEST_S3_IMAGE="umbod-kind-s3:ci"
    case "$(docker info --format '{{.Architecture}}')" in
        aarch64|arm64) s3_image_digest="sha256:b5ca2f8161b8fb51c44a035ab7709e77faec74c3eb21580beef11b3a8cc3387c" ;;
        x86_64|amd64) s3_image_digest="sha256:42d1514525b3c60ad77b1347a4f2733c1953016e72424dc5ea7a9d59dc8c45b3" ;;
        *) printf '%s\n' 'Unsupported Docker architecture for the test S3 fixture' >&2; exit 1 ;;
    esac
    s3_fixture_image="cgr.dev/chainguard/minio@${s3_image_digest}"
    docker pull "${s3_fixture_image}"
    docker tag "${s3_fixture_image}" "${UMBOD_TEST_S3_IMAGE}"
fi

docker build --tag ghcr.io/computerlovetech/umbod:ci --file "${app_directory}/api/Dockerfile" "${repository_directory}"
docker build --tag ghcr.io/computerlovetech/umbod-frontend:ci "${app_directory}/frontend"
docker build --tag umbod-kind-test-connector:ci "${script_directory}/connector"

kind create cluster --name "${cluster_name}" --image "${UMBOD_KIND_NODE_IMAGE:-kindest/node:v1.32.2}" --wait 2m
cluster_created=true
kind load docker-image --name "${cluster_name}" ghcr.io/computerlovetech/umbod:ci ghcr.io/computerlovetech/umbod-frontend:ci umbod-kind-test-connector:ci

if [[ "${UMBOD_TEST_CONTENT_BACKEND}" == "s3" ]]; then
    kind load docker-image --name "${cluster_name}" "${UMBOD_TEST_S3_IMAGE}"
fi

kubectl --context "${kube_context}" create secret generic umbod-ci \
    --from-literal="UMBOD_MCP_TEST_BEARER_TOKEN=${UMBOD_TEST_BEARER_TOKEN}" \
    --from-literal="UMBOD_MCP_TEST_BEARER_TOKEN_B=${UMBOD_TEST_BEARER_TOKEN_B}" \
    --from-literal="UMBOD_ROOT_SECRET=${UMBOD_TEST_ROOT_SECRET}"
kubectl --context "${kube_context}" create secret generic umbod-collector-ci \
    --from-literal="token=${UMBOD_TEST_OTLP_BEARER_TOKEN}"
helm --kube-context "${kube_context}" install "${release_name}" "${chart_directory}" \
    --values "${chart_directory}/ci/kind-values.yaml" \
    --values "${script_directory}/values.yaml" \
    --set "config.filesystem.previewMaxBytes=${UMBOD_TEST_FILESYSTEM_PREVIEW_MAX_BYTES}" \
    --set-string "core.mcp.administrator.baseUrl=${UMBOD_TEST_ADMIN_MCP_URL%/mcp}" \
    --wait --timeout 5m
helm --kube-context "${kube_context}" test "${release_name}" --logs --timeout 2m

if [[ "${UMBOD_TEST_CONTENT_BACKEND}" == "s3" ]]; then
    python3 "${script_directory}/setup_s3_runtime.py"
fi

kubectl --context "${kube_context}" set env deployment/umbod-core --containers=mcp \
    UMBOD_MCP_TOOL_EXPOSURE=flat UMBOD_MCP_STATELESS_HTTP=false UMBOD_MCP_PERMISSION_CLAIM=groups
kubectl --context "${kube_context}" set env deployment/umbod-core --containers=api \
    UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED=true
kubectl --context "${kube_context}" rollout status deployment/umbod-core --timeout=3m

kubectl --context "${kube_context}" port-forward service/umbod-api "${api_port}:8000" --address 127.0.0.1 &
api_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp "${mcp_port}:8011" --address 127.0.0.1 &
mcp_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp-administrator "${admin_mcp_port}:8017" --address 127.0.0.1 &
admin_mcp_forward_pid=$!

kubectl --context "${kube_context}" port-forward service/umbod-telemetry "${otlp_port}:4318" --address 127.0.0.1 &
otlp_forward_pid=$!

for attempt in $(seq 1 30); do
    if curl --fail --silent "${UMBOD_TEST_API_BASE_URL}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_MCP_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_ADMIN_MCP_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_OTLP_BASE_URL}/ready" >/dev/null; then
        break
    fi
    if [[ ${attempt} -eq 30 ]]; then
        printf '%s\n' 'Kind runtime port-forwards did not become healthy' >&2
        exit 1
    fi
    sleep 1
done

python3 "${script_directory}/bootstrap.py"
(cd "${app_directory}/api" && uv run --locked pytest live_runtime_tests --ignore=live_runtime_tests/test_running_personal_usage.py --ignore=live_runtime_tests/test_running_personal_mcp_execution.py --ignore=live_runtime_tests/test_running_personal_oauth_setup.py --ignore=live_runtime_tests/test_running_personal_oauth_policy.py --ignore=live_runtime_tests/test_running_personal_tools_policy.py --ignore=live_runtime_tests/test_running_user_catalogue.py --ignore=live_runtime_tests/test_running_user_profile.py --ignore=live_runtime_tests/test_running_filesystem.py --ignore=live_runtime_tests/test_running_filesystem_uploads.py --ignore=live_runtime_tests/test_running_filesystem_homes.py --ignore=live_runtime_tests/test_running_filesystem_s3.py --ignore=live_runtime_tests/test_running_provider_group_mappings.py)
kubectl --context "${kube_context}" logs deployment/umbod-core --container api \
    | python3 "${script_directory}/check_telemetry_logs.py"
kubectl --context "${kube_context}" exec -i deployment/umbod-core --container api -- python - \
    < "${script_directory}/check_analytics.py"
kubectl --context "${kube_context}" logs deployment/umbod-core --container mcp \
    | python3 "${script_directory}/check_secret_logs.py"

for forward_pid in "${api_forward_pid}" "${mcp_forward_pid}" "${admin_mcp_forward_pid}" "${otlp_forward_pid}"; do
    kill "${forward_pid}" 2>/dev/null || true
    wait "${forward_pid}" 2>/dev/null || true
done
api_forward_pid=""
mcp_forward_pid=""
admin_mcp_forward_pid=""
otlp_forward_pid=""
(cd "${app_directory}/api" && uv run --locked python "${script_directory}/setup_personal_runtime.py" "${host_temporary_directory}")
IFS= read -r UMBOD_TEST_BEARER_TOKEN < "${host_temporary_directory}/bearer-a"
IFS= read -r UMBOD_TEST_BEARER_TOKEN_B < "${host_temporary_directory}/bearer-b"
IFS= read -r UMBOD_TEST_MEMBER_BEARER_TOKEN < "${host_temporary_directory}/bearer-member"
export UMBOD_TEST_BEARER_TOKEN UMBOD_TEST_BEARER_TOKEN_B UMBOD_TEST_MEMBER_BEARER_TOKEN
kubectl --context "${kube_context}" port-forward service/umbod-api "${api_port}:8000" --address 127.0.0.1 &
api_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp "${mcp_port}:8011" --address 127.0.0.1 &
mcp_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-mcp-administrator "${admin_mcp_port}:8017" --address 127.0.0.1 &
admin_mcp_forward_pid=$!
kubectl --context "${kube_context}" port-forward deployment/umbod-core "${UMBOD_TEST_MCP_B_PORT:-28013}:8013" --address 127.0.0.1 &
mcp_b_forward_pid=$!
kubectl --context "${kube_context}" port-forward deployment/umbod-core "${UMBOD_TEST_API_B_PORT:-28015}:8015" --address 127.0.0.1 &
api_b_forward_pid=$!
kubectl --context "${kube_context}" port-forward service/umbod-telemetry "${otlp_port}:4318" --address 127.0.0.1 &
otlp_forward_pid=$!
kubectl --context "${kube_context}" port-forward deployment/personal-runtime "${UMBOD_TEST_PERSONAL_PORT:-28443}:8443" --address 127.0.0.1 &
fixture_forward_pid=$!
for attempt in $(seq 1 60); do
    if curl --fail --silent "${UMBOD_TEST_API_BASE_URL}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_MCP_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_ADMIN_MCP_URL%/mcp}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_API_B_BASE_URL}/system/health" >/dev/null \
        && curl --fail --silent "${UMBOD_TEST_OTLP_BASE_URL}/ready" >/dev/null \
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
(cd "${app_directory}/api" && uv run --locked pytest -n 0 --tb=short live_runtime_tests/test_running_provider_group_mappings.py)
(cd "${app_directory}/api" && uv run --locked python -c '
import os
import runpy
from urllib.request import build_opener, install_opener
opener = build_opener()
opener.addheaders = [("Authorization", "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN"])]
install_opener(opener)
bootstrap = runpy.run_path(os.environ["UMBOD_TEST_BOOTSTRAP_PATH"])
bootstrap["main"]()
bootstrap["seed_signed_group_mappings"](os.environ["UMBOD_TEST_API_BASE_URL"])
')
(cd "${app_directory}/api" && uv run --locked pytest -n 0 --tb=short live_runtime_tests/test_running_personal_usage.py live_runtime_tests/test_running_mcp_administrator_hosting.py live_runtime_tests/test_running_user_profile.py live_runtime_tests/test_running_personal_access_tokens.py live_runtime_tests/test_running_personal_mcp_execution.py live_runtime_tests/test_running_personal_oauth_setup.py live_runtime_tests/test_running_personal_oauth_policy.py live_runtime_tests/test_running_personal_tools_policy.py live_runtime_tests/test_running_user_catalogue.py live_runtime_tests/test_running_filesystem.py live_runtime_tests/test_running_filesystem_uploads.py live_runtime_tests/test_running_filesystem_homes.py live_runtime_tests/test_running_filesystem_sharing.py live_runtime_tests/test_running_filesystem_s3.py live_runtime_tests/test_running_identity_directory.py)
for container_name in api api-b mcp mcp-b; do
    kubectl --context "${kube_context}" logs deployment/umbod-core --container "${container_name}" \
        | python3 "${script_directory}/check_secret_logs.py"
done
