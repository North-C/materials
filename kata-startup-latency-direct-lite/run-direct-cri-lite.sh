#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../../.." && pwd)

RESULTS_ROOT="${RESULTS_ROOT:-${REPO_ROOT}/results-direct-lite}"
DIRECT_LITE_NAMESPACE="${DIRECT_LITE_NAMESPACE:-default}"
DIRECT_LITE_RUNTIME_HANDLER="${DIRECT_LITE_RUNTIME_HANDLER:-kata}"
DIRECT_LITE_IMAGE="${DIRECT_LITE_IMAGE:-sealos.hub:5000/pause:3.9}"
DIRECT_LITE_HYPERVISOR="${DIRECT_LITE_HYPERVISOR:-cloud-hypervisor}"
DIRECT_LITE_CLEANUP="${DIRECT_LITE_CLEANUP:-true}"
DIRECT_LITE_LOG_FLUSH_WAIT_SECS="${DIRECT_LITE_LOG_FLUSH_WAIT_SECS:-2}"
DIRECT_LITE_SANDBOX_TEMPLATE="${DIRECT_LITE_SANDBOX_TEMPLATE:-${SCRIPT_DIR}/manifests/crictl-sandbox.json}"
DIRECT_LITE_CONTAINER_TEMPLATE="${DIRECT_LITE_CONTAINER_TEMPLATE:-${SCRIPT_DIR}/manifests/crictl-container.json}"

die() {
	echo "[$(basename "$0")] ERROR: $*" >&2
	exit 1
}

require_cmd() {
	command -v "$1" > /dev/null 2>&1 || die "command not available: $1"
}

utc_timestamp() {
	date -u +"%Y-%m-%dT%H:%M:%S.%NZ"
}

local_timestamp() {
	date +"%Y-%m-%d %H:%M:%S"
}

generate_run_id() {
	date -u +"run-%Y%m%dT%H%M%SZ"
}

RUN_ID=$(generate_run_id)
RUN_DIR="${RESULTS_ROOT}/$(date -u +%F)/${RUN_ID}"
NAME_SUFFIX=$(date -u +%H%M%S)
SANDBOX_NAME="kata-direct-lite-sandbox-${NAME_SUFFIX}"
CONTAINER_NAME="kata-direct-lite-container-${NAME_SUFFIX}"
SANDBOX_UID="kata-direct-lite-${NAME_SUFFIX}"
SANDBOX_CFG="${RUN_DIR}/workloads/${SANDBOX_NAME}-sandbox.json"
CONTAINER_CFG="${RUN_DIR}/workloads/${CONTAINER_NAME}-container.json"
REQUEST_FILE="${RUN_DIR}/raw/request.json"
INSPECTP_JSON="${RUN_DIR}/raw/inspectp.json"
INSPECT_JSON="${RUN_DIR}/raw/inspect.json"

require_cmd crictl
require_cmd sed
require_cmd python3

mkdir -p "${RUN_DIR}/raw" "${RUN_DIR}/logs" "${RUN_DIR}/summary" "${RUN_DIR}/workloads"

sed \
	-e "s/__SANDBOX_NAME__/${SANDBOX_NAME}/g" \
	-e "s/__SANDBOX_UID__/${SANDBOX_UID}/g" \
	-e "s/__NAMESPACE__/${DIRECT_LITE_NAMESPACE}/g" \
	"${DIRECT_LITE_SANDBOX_TEMPLATE}" > "${SANDBOX_CFG}"

sed \
	-e "s/__CONTAINER_NAME__/${CONTAINER_NAME}/g" \
	-e "s/__NAMESPACE__/${DIRECT_LITE_NAMESPACE}/g" \
	-e "s#__IMAGE__#${DIRECT_LITE_IMAGE}#g" \
	"${DIRECT_LITE_CONTAINER_TEMPLATE}" > "${CONTAINER_CFG}"

REQUEST_SENT_UTC=$(utc_timestamp)
REQUEST_SENT_LOCAL=$(local_timestamp)

cat > "${REQUEST_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "workload_type": "direct_kata_container",
  "sandbox_name": "${SANDBOX_NAME}",
  "container_name": "${CONTAINER_NAME}",
  "namespace": "${DIRECT_LITE_NAMESPACE}",
  "runtime_handler": "${DIRECT_LITE_RUNTIME_HANDLER}",
  "hypervisor": "${DIRECT_LITE_HYPERVISOR}",
  "t_request_sent": "${REQUEST_SENT_UTC}"
}
EOF

SANDBOX_ID=$(sudo crictl runp --runtime "${DIRECT_LITE_RUNTIME_HANDLER}" "${SANDBOX_CFG}")
CONTAINER_ID=$(sudo crictl create "${SANDBOX_ID}" "${CONTAINER_CFG}" "${SANDBOX_CFG}")
sudo crictl start "${CONTAINER_ID}" > /dev/null
sudo crictl inspectp "${SANDBOX_ID}" > "${INSPECTP_JSON}"
sudo crictl inspect "${CONTAINER_ID}" > "${INSPECT_JSON}"

sleep "${DIRECT_LITE_LOG_FLUSH_WAIT_SECS}"
UNTIL_LOCAL=$(local_timestamp)
bash "${SCRIPT_DIR}/collect-logs-lite.sh" --run-dir "${RUN_DIR}" --since "${REQUEST_SENT_LOCAL}" --until "${UNTIL_LOCAL}"
python3 "${SCRIPT_DIR}/parse_direct_kata_latency.py" --run-dir "${RUN_DIR}" > /dev/null

if [[ "${DIRECT_LITE_CLEANUP}" == "true" ]]; then
	sudo crictl stop "${CONTAINER_ID}" > /dev/null 2>&1 || true
	sudo crictl rm "${CONTAINER_ID}" > /dev/null 2>&1 || true
	sudo crictl stopp "${SANDBOX_ID}" > /dev/null 2>&1 || true
	sudo crictl rmp "${SANDBOX_ID}" > /dev/null 2>&1 || true
fi

printf "%s\n" "${RUN_DIR}"
