#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../../.." && pwd)

RESULTS_ROOT="${RESULTS_ROOT:-${REPO_ROOT}/results-lite}"
LITE_NAMESPACE="${LITE_NAMESPACE:-default}"
LITE_RUNTIME_CLASS="${LITE_RUNTIME_CLASS:-kata}"
LITE_IMAGE="${LITE_IMAGE:-sealos.hub:5000/pause:3.9}"
LITE_HYPERVISOR="${LITE_HYPERVISOR:-cloud-hypervisor}"
LITE_DELETE_POD="${LITE_DELETE_POD:-true}"
K8S_APISERVER_NO_PROXY="${K8S_APISERVER_NO_PROXY:-apiserver.cluster.local,100.125.62.182,127.0.0.1,localhost}"

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

kubectl_safe() {
	NO_PROXY="${K8S_APISERVER_NO_PROXY},${NO_PROXY:-}" \
	HTTPS_PROXY= \
	HTTP_PROXY= \
	ALL_PROXY= \
	kubectl "$@"
}

RUN_ID=$(generate_run_id)
RUN_DIR="${RESULTS_ROOT}/$(date -u +%F)/${RUN_ID}"
POD_NAME="kata-lite-$(date -u +%H%M%S)"
MANIFEST="${RUN_DIR}/workloads/${POD_NAME}.yaml"
REQUEST_FILE="${RUN_DIR}/raw/request.json"
POD_JSON="${RUN_DIR}/raw/pod.json"
EVENTS_JSON="${RUN_DIR}/raw/events.json"
DESCRIBE_TXT="${RUN_DIR}/raw/pod-describe.txt"

require_cmd kubectl
require_cmd sed
require_cmd python3

mkdir -p "${RUN_DIR}/raw" "${RUN_DIR}/logs" "${RUN_DIR}/summary" "${RUN_DIR}/workloads"

sed \
	-e "s/__POD_NAME__/${POD_NAME}/g" \
	-e "s/__NAMESPACE__/${LITE_NAMESPACE}/g" \
	-e "s/__RUNTIME_CLASS__/${LITE_RUNTIME_CLASS}/g" \
	-e "s#__IMAGE__#${LITE_IMAGE}#g" \
	"${SCRIPT_DIR}/manifests/kata-latency-pod.yaml" > "${MANIFEST}"

REQUEST_SENT_UTC=$(utc_timestamp)
REQUEST_SENT_LOCAL=$(local_timestamp)

cat > "${REQUEST_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "workload_type": "k8s_pod",
  "pod_name": "${POD_NAME}",
  "namespace": "${LITE_NAMESPACE}",
  "runtime_handler": "${LITE_RUNTIME_CLASS}",
  "hypervisor": "${LITE_HYPERVISOR}",
  "t_request_sent": "${REQUEST_SENT_UTC}"
}
EOF

kubectl_safe apply -f "${MANIFEST}"
kubectl_safe wait --for=condition=Ready "pod/${POD_NAME}" -n "${LITE_NAMESPACE}" --timeout=120s
kubectl_safe get "pod/${POD_NAME}" -n "${LITE_NAMESPACE}" -o json > "${POD_JSON}"
kubectl_safe get events -n "${LITE_NAMESPACE}" --field-selector "involvedObject.name=${POD_NAME}" -o json > "${EVENTS_JSON}" || true
kubectl_safe describe "pod/${POD_NAME}" -n "${LITE_NAMESPACE}" > "${DESCRIBE_TXT}"

UNTIL_LOCAL=$(local_timestamp)
bash "${SCRIPT_DIR}/collect-logs-lite.sh" --run-dir "${RUN_DIR}" --since "${REQUEST_SENT_LOCAL}" --until "${UNTIL_LOCAL}"
python3 "${SCRIPT_DIR}/parse_kata_pod_latency.py" --run-dir "${RUN_DIR}" > /dev/null

if [[ "${LITE_DELETE_POD}" == "true" ]]; then
	kubectl_safe delete "pod/${POD_NAME}" -n "${LITE_NAMESPACE}" --wait=true --timeout=120s || true
fi

printf "%s\n" "${RUN_DIR}"
