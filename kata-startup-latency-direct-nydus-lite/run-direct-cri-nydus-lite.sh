#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../../.." && pwd)

RESULTS_ROOT="${RESULTS_ROOT:-${REPO_ROOT}/results-direct-nydus-lite}"
DIRECT_NYDUS_NAMESPACE="${DIRECT_NYDUS_NAMESPACE:-default}"
DIRECT_NYDUS_RUNTIME_HANDLER="${DIRECT_NYDUS_RUNTIME_HANDLER:-kata}"
DIRECT_NYDUS_SOURCE_IMAGE="${DIRECT_NYDUS_SOURCE_IMAGE:-sealos.hub:5000/pause:3.9}"
DIRECT_NYDUS_HYPERVISOR="${DIRECT_NYDUS_HYPERVISOR:-cloud-hypervisor}"
DIRECT_NYDUS_BASE_KATA_CONFIG="${DIRECT_NYDUS_BASE_KATA_CONFIG:-/opt/kata/share/defaults/kata-containers/configuration-clh.toml}"
DIRECT_NYDUS_CLEANUP="${DIRECT_NYDUS_CLEANUP:-true}"
DIRECT_NYDUS_LOG_FLUSH_WAIT_SECS="${DIRECT_NYDUS_LOG_FLUSH_WAIT_SECS:-2}"
DIRECT_NYDUS_CONTAINERD_CONFIG="${DIRECT_NYDUS_CONTAINERD_CONFIG:-/etc/containerd/config.toml}"
DIRECT_NYDUS_SNAPSHOTTER_CONFIG="${DIRECT_NYDUS_SNAPSHOTTER_CONFIG:-/etc/nydus-snapshotter/config.toml}"
DIRECT_NYDUS_SANDBOX_TEMPLATE="${DIRECT_NYDUS_SANDBOX_TEMPLATE:-${SCRIPT_DIR}/manifests/crictl-sandbox.json}"
DIRECT_NYDUS_CONTAINER_TEMPLATE="${DIRECT_NYDUS_CONTAINER_TEMPLATE:-${SCRIPT_DIR}/manifests/crictl-container.json}"
DIRECT_NYDUS_TARGET_TAG="${DIRECT_NYDUS_TARGET_TAG:-nydus-lite}"
DIRECT_NYDUS_REGISTRY="${DIRECT_NYDUS_REGISTRY:-sealos.hub:5000}"
DIRECT_NYDUS_REGISTRY_USER="${DIRECT_NYDUS_REGISTRY_USER:-admin}"
DIRECT_NYDUS_REGISTRY_PASSWORD="${DIRECT_NYDUS_REGISTRY_PASSWORD:-passw0rd}"

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

sanitize_ref_fragment() {
	printf "%s" "$1" | tr '/:@' '-' | tr -cd '[:alnum:]._-'
}

derive_target_ref() {
	local safe_name
	safe_name=$(sanitize_ref_fragment "$1")
	printf "localhost/kata-direct-nydus/%s:%s" "${safe_name}" "${DIRECT_NYDUS_TARGET_TAG}"
}

derive_registry_ref() {
	local safe_name
	safe_name=$(sanitize_ref_fragment "$1")
	printf "%s/kata-direct-nydus/%s:%s" "${DIRECT_NYDUS_REGISTRY}" "${safe_name}" "${DIRECT_NYDUS_TARGET_TAG}"
}

wait_for_containerd_ready() {
	local deadline=$((SECONDS + 60))
	while (( SECONDS < deadline )); do
		if sudo crictl info > /dev/null 2>&1; then
			return 0
		fi
		sleep 2
	done
	return 1
}

read_json_value() {
	local json_file="$1"
	local expression="$2"
	python3 - "$json_file" "$expression" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
expr = sys.argv[2].split(".")
cur = data
for part in expr:
    if not part:
        continue
    if isinstance(cur, dict):
        cur = cur.get(part, "")
    else:
        cur = ""
        break
if cur is None:
    cur = ""
print(cur)
PY
}

patch_containerd_config() {
	local source_file="$1"
	local target_file="$2"
	local sandbox_image="$3"
	local kata_config_path="$4"
	python3 - "$source_file" "$target_file" "$sandbox_image" "$kata_config_path" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
sandbox_image = sys.argv[3]
kata_config_path = sys.argv[4]
text = src.read_text(encoding="utf-8")

text, snapshotter_hits = re.subn(
    r'(?m)^(\s*snapshotter\s*=\s*)".*"$',
    r'\1"nydus"',
    text,
    count=1,
)
text, sandbox_hits = re.subn(
    r'(?m)^(\s*sandbox_image\s*=\s*)".*"$',
    rf'\1"{sandbox_image}"',
    text,
    count=1,
)
text, _ = re.subn(
    r'(?m)^(\s*disable_snapshot_annotations\s*=\s*)true$',
    r'\1false',
    text,
)

kata_header = '[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata]'
header_index = text.find(kata_header)
if header_index < 0:
    raise SystemExit("failed to find kata runtime block in containerd config")
block_start = header_index + len(kata_header) + 1
next_header = text.find("\n        [plugins.", block_start)
if next_header < 0:
    next_header = len(text)
kata_block = text[block_start:next_header]
if re.search(r'(?m)^(\s*)snapshotter\s*=', kata_block):
    kata_block = re.sub(
        r'(?m)^(\s*snapshotter\s*=\s*)".*"$',
        r'\1"nydus"',
        kata_block,
        count=1,
    )
else:
    kata_block = '          snapshotter = "nydus"\n' + kata_block
text = text[:block_start] + kata_block + text[next_header:]

kata_options_header = '[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata.options]'
options_header_index = text.find(kata_options_header)
if options_header_index < 0:
    raise SystemExit("failed to find kata options block in containerd config")
options_block_start = options_header_index + len(kata_options_header) + 1
next_header = text.find("\n        [plugins.", options_block_start)
if next_header < 0:
    next_header = len(text)
options_block = text[options_block_start:next_header]
if re.search(r'(?m)^(\s*)ConfigPath\s*=', options_block):
    options_block = re.sub(
        r'(?m)^(\s*ConfigPath\s*=\s*)".*"$',
        rf'\1"{kata_config_path}"',
        options_block,
        count=1,
    )
else:
    options_block = f'            ConfigPath = "{kata_config_path}"\n' + options_block
text = text[:options_block_start] + options_block + text[next_header:]

if snapshotter_hits != 1:
    raise SystemExit("failed to patch containerd snapshotter")
if sandbox_hits != 1:
    raise SystemExit("failed to patch sandbox_image")

dst.write_text(text, encoding="utf-8")
PY
}

patch_kata_config() {
	local source_file="$1"
	local target_file="$2"
	python3 - "$source_file" "$target_file" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")

replacements = [
    (r'(?m)^shared_fs\s*=.*$', 'shared_fs = "virtio-fs-nydus"'),
    (r'(?m)^virtio_fs_daemon\s*=.*$', 'virtio_fs_daemon = "/usr/local/bin/nydusd"'),
    (r'(?m)^virtio_fs_extra_args\s*=.*$', 'virtio_fs_extra_args = []'),
]

for pattern, replacement in replacements:
    text, hits = re.subn(pattern, replacement, text, count=1)
    if hits != 1:
        raise SystemExit(f"failed to patch Kata config with pattern: {pattern}")

dst.write_text(text, encoding="utf-8")
PY
}

patch_nydus_snapshotter_config() {
	local source_file="$1"
	local target_file="$2"
	python3 - "$source_file" "$target_file" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")

if "[snapshot]" not in text:
    text += "\n[snapshot]\n  enable_nydus_overlayfs = true\n"
elif re.search(r'(?m)^(\s*)enable_nydus_overlayfs\s*=', text):
    text = re.sub(
        r'(?m)^(\s*enable_nydus_overlayfs\s*=\s*)false$',
        r'\1true',
        text,
        count=1,
    )
else:
    text = text.replace("[snapshot]\n", "[snapshot]\n  enable_nydus_overlayfs = true\n", 1)

dst.write_text(text, encoding="utf-8")
PY
}

convert_local_image_to_nydus() {
	local source_image="$1"
	local target_image="$2"
	local source_archive="$3"
	local target_archive="$4"
	local metrics_json="$5"
	local work_dir="$6"

	sudo ctr -n k8s.io images export "${source_archive}" "${source_image}"
	nydusify convert \
		--source "${source_image}" \
		--source-archive "${source_archive}" \
		--target-archive "${target_archive}" \
		--target "${target_image}" \
		--merge-platform \
		--work-dir "${work_dir}" \
		--output-json "${metrics_json}" \
		--oci
	test -s "${target_archive}" || die "nydus target archive not created for ${source_image}"
	test -s "${metrics_json}" || die "nydus conversion metrics missing for ${source_image}"
	sudo ctr -n k8s.io images import --no-unpack "${target_archive}"
	sudo ctr -n k8s.io images label "${target_image}" io.cri-containerd.image=managed > /dev/null
}

try_cri_inspect_image() {
	local image_ref="$1"
	sudo crictl inspecti "${image_ref}" > /dev/null 2>&1
}

publish_image_via_nerdctl() {
	local local_ref="$1"
	local remote_ref="$2"

	sudo nerdctl --namespace k8s.io login \
		-u "${DIRECT_NYDUS_REGISTRY_USER}" \
		-p "${DIRECT_NYDUS_REGISTRY_PASSWORD}" \
		--insecure-registry \
		"${DIRECT_NYDUS_REGISTRY}" > /dev/null
	sudo nerdctl --namespace k8s.io tag "${local_ref}" "${remote_ref}"
	sudo nerdctl --namespace k8s.io --insecure-registry push "${remote_ref}" > /dev/null
	sudo crictl pull "${remote_ref}" > /dev/null
	try_cri_inspect_image "${remote_ref}" || die "CRI still cannot resolve pushed image: ${remote_ref}"
}

ensure_runtime_image_ref() {
	local source_image="$1"
	local local_ref="$2"
	local remote_ref="$3"

	if try_cri_inspect_image "${local_ref}"; then
		printf "%s\n" "${local_ref}"
		return 0
	fi

	publish_image_via_nerdctl "${local_ref}" "${remote_ref}"
	printf "%s\n" "${remote_ref}"
}

validate_result() {
	local run_dir="$1"
	python3 - "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads((Path(sys.argv[1]) / "summary" / "result.json").read_text(encoding="utf-8"))
checks = [
    result.get("validation_snapshotter_is_nydus"),
    result.get("validation_kata_config_is_clh"),
    result.get("validation_effective_image_matches_request"),
    result.get("validation_nydus_log_seen"),
]
if not all(checks):
    raise SystemExit(
        "direct-nydus-lite validation failed: "
        + json.dumps(
            {
                "validation_snapshotter_is_nydus": result.get("validation_snapshotter_is_nydus"),
                "validation_kata_config_is_clh": result.get("validation_kata_config_is_clh"),
                "validation_effective_image_matches_request": result.get("validation_effective_image_matches_request"),
                "validation_nydus_log_seen": result.get("validation_nydus_log_seen"),
            },
            sort_keys=True,
        )
    )
PY
}

RUN_ID=$(generate_run_id)
RUN_DIR="${RESULTS_ROOT}/$(date -u +%F)/${RUN_ID}"
NAME_SUFFIX=$(date -u +%H%M%S)
SANDBOX_NAME="kata-direct-nydus-lite-sandbox-${NAME_SUFFIX}"
CONTAINER_NAME="kata-direct-nydus-lite-container-${NAME_SUFFIX}"
SANDBOX_UID="kata-direct-nydus-lite-${NAME_SUFFIX}"
APP_EFFECTIVE_IMAGE="${DIRECT_NYDUS_TARGET_IMAGE:-$(derive_target_ref "${DIRECT_NYDUS_SOURCE_IMAGE}")}"
APP_RUNTIME_IMAGE=""
SANDBOX_SOURCE_IMAGE=""
SANDBOX_EFFECTIVE_IMAGE=""
SANDBOX_RUNTIME_IMAGE=""
SANDBOX_ID=""
CONTAINER_ID=""
REQUEST_SENT_LOCAL=""
CONTAINERD_RESTORE_NEEDED="false"

APP_REGISTRY_IMAGE="${DIRECT_NYDUS_REGISTRY_IMAGE:-$(derive_registry_ref "${DIRECT_NYDUS_SOURCE_IMAGE}")}"
SANDBOX_REGISTRY_IMAGE=""

REQUEST_FILE="${RUN_DIR}/raw/request.json"
INSPECTP_JSON="${RUN_DIR}/raw/inspectp.json"
INSPECT_JSON="${RUN_DIR}/raw/inspect.json"
CRI_INFO_BEFORE_JSON="${RUN_DIR}/raw/crictl-info.before.json"
CRI_INFO_AFTER_JSON="${RUN_DIR}/raw/crictl-info.after.json"
SANDBOX_IMAGE_INFO_JSON="${RUN_DIR}/raw/sandbox-image.json"
APP_IMAGE_INFO_JSON="${RUN_DIR}/raw/app-image.json"
APP_SOURCE_ARCHIVE="${RUN_DIR}/raw/app-source-image.tar"
APP_TARGET_ARCHIVE="${RUN_DIR}/raw/app-nydus-image.tar"
APP_CONVERT_METRICS="${RUN_DIR}/raw/app-nydus-convert.json"
SANDBOX_SOURCE_ARCHIVE="${RUN_DIR}/raw/sandbox-source-image.tar"
SANDBOX_TARGET_ARCHIVE="${RUN_DIR}/raw/sandbox-nydus-image.tar"
SANDBOX_CONVERT_METRICS="${RUN_DIR}/raw/sandbox-nydus-convert.json"
PATCHED_NYDUS_SNAPSHOTTER_CONFIG="${RUN_DIR}/config/nydus-snapshotter-config.toml.patched"
NYDUS_SNAPSHOTTER_CONFIG_BACKUP="${RUN_DIR}/config/nydus-snapshotter-config.toml.before"
PATCHED_CONTAINERD_CONFIG="${RUN_DIR}/config/containerd-config.toml.patched"
CONTAINERD_CONFIG_BACKUP="${RUN_DIR}/config/containerd-config.toml.before"
PATCHED_KATA_CONFIG="${RUN_DIR}/config/configuration-clh-nydus.toml"
SANDBOX_CFG="${RUN_DIR}/workloads/${SANDBOX_NAME}-sandbox.json"
CONTAINER_CFG="${RUN_DIR}/workloads/${CONTAINER_NAME}-container.json"
WORK_DIR="${RUN_DIR}/workdir"
NYDUS_SNAPSHOTTER_RESTORE_NEEDED="false"

cleanup_resources() {
	if [[ "${DIRECT_NYDUS_CLEANUP}" != "true" ]]; then
		return 0
	fi
	if [[ -n "${CONTAINER_ID}" ]]; then
		sudo crictl stop "${CONTAINER_ID}" > /dev/null 2>&1 || true
		sudo crictl rm "${CONTAINER_ID}" > /dev/null 2>&1 || true
	fi
	if [[ -n "${SANDBOX_ID}" ]]; then
		sudo crictl stopp "${SANDBOX_ID}" > /dev/null 2>&1 || true
		sudo crictl rmp "${SANDBOX_ID}" > /dev/null 2>&1 || true
	fi
}

restore_containerd_config() {
	if [[ "${CONTAINERD_RESTORE_NEEDED}" != "true" ]]; then
		return 0
	fi
	sudo cp "${CONTAINERD_CONFIG_BACKUP}" "${DIRECT_NYDUS_CONTAINERD_CONFIG}"
	sudo systemctl restart containerd
	wait_for_containerd_ready || die "containerd did not recover after restore"
	CONTAINERD_RESTORE_NEEDED="false"
}

restore_nydus_snapshotter_config() {
	if [[ "${NYDUS_SNAPSHOTTER_RESTORE_NEEDED}" != "true" ]]; then
		return 0
	fi
	sudo cp "${NYDUS_SNAPSHOTTER_CONFIG_BACKUP}" "${DIRECT_NYDUS_SNAPSHOTTER_CONFIG}"
	sudo systemctl restart nydus-snapshotter
	NYDUS_SNAPSHOTTER_RESTORE_NEEDED="false"
}

on_exit() {
	local exit_code=$?
	cleanup_resources || true
	restore_containerd_config || true
	restore_nydus_snapshotter_config || true
	exit "${exit_code}"
}

trap on_exit EXIT

require_cmd crictl
require_cmd ctr
require_cmd journalctl
require_cmd nydusify
require_cmd python3
require_cmd sed
require_cmd sudo

mkdir -p "${RUN_DIR}/raw" "${RUN_DIR}/logs" "${RUN_DIR}/summary" "${RUN_DIR}/workloads" "${RUN_DIR}/config" "${WORK_DIR}"

sudo crictl info > "${CRI_INFO_BEFORE_JSON}"
SANDBOX_SOURCE_IMAGE=$(read_json_value "${CRI_INFO_BEFORE_JSON}" "config.sandboxImage")
[ -n "${SANDBOX_SOURCE_IMAGE}" ] || die "unable to determine current sandbox image"
SANDBOX_EFFECTIVE_IMAGE=$(derive_target_ref "${SANDBOX_SOURCE_IMAGE}")

sudo crictl inspecti "${DIRECT_NYDUS_SOURCE_IMAGE}" > "${APP_IMAGE_INFO_JSON}"
sudo crictl inspecti "${SANDBOX_SOURCE_IMAGE}" > "${SANDBOX_IMAGE_INFO_JSON}"

patch_kata_config "${DIRECT_NYDUS_BASE_KATA_CONFIG}" "${PATCHED_KATA_CONFIG}"
sudo cp "${DIRECT_NYDUS_SNAPSHOTTER_CONFIG}" "${NYDUS_SNAPSHOTTER_CONFIG_BACKUP}"
patch_nydus_snapshotter_config "${NYDUS_SNAPSHOTTER_CONFIG_BACKUP}" "${PATCHED_NYDUS_SNAPSHOTTER_CONFIG}"
sudo cp "${PATCHED_NYDUS_SNAPSHOTTER_CONFIG}" "${DIRECT_NYDUS_SNAPSHOTTER_CONFIG}"
sudo systemctl restart nydus-snapshotter
NYDUS_SNAPSHOTTER_RESTORE_NEEDED="true"

convert_local_image_to_nydus \
	"${DIRECT_NYDUS_SOURCE_IMAGE}" \
	"${APP_EFFECTIVE_IMAGE}" \
	"${APP_SOURCE_ARCHIVE}" \
	"${APP_TARGET_ARCHIVE}" \
	"${APP_CONVERT_METRICS}" \
	"${WORK_DIR}/app"
APP_RUNTIME_IMAGE=$(ensure_runtime_image_ref "${DIRECT_NYDUS_SOURCE_IMAGE}" "${APP_EFFECTIVE_IMAGE}" "${APP_REGISTRY_IMAGE}")

if [[ "${SANDBOX_SOURCE_IMAGE}" == "${DIRECT_NYDUS_SOURCE_IMAGE}" ]]; then
	SANDBOX_EFFECTIVE_IMAGE="${APP_EFFECTIVE_IMAGE}"
	SANDBOX_RUNTIME_IMAGE="${APP_RUNTIME_IMAGE}"
	SANDBOX_REGISTRY_IMAGE="${APP_REGISTRY_IMAGE}"
	cp "${APP_CONVERT_METRICS}" "${SANDBOX_CONVERT_METRICS}"
else
	SANDBOX_REGISTRY_IMAGE=$(derive_registry_ref "${SANDBOX_SOURCE_IMAGE}")
	convert_local_image_to_nydus \
		"${SANDBOX_SOURCE_IMAGE}" \
		"${SANDBOX_EFFECTIVE_IMAGE}" \
		"${SANDBOX_SOURCE_ARCHIVE}" \
		"${SANDBOX_TARGET_ARCHIVE}" \
		"${SANDBOX_CONVERT_METRICS}" \
		"${WORK_DIR}/sandbox"
	SANDBOX_RUNTIME_IMAGE=$(ensure_runtime_image_ref "${SANDBOX_SOURCE_IMAGE}" "${SANDBOX_EFFECTIVE_IMAGE}" "${SANDBOX_REGISTRY_IMAGE}")
fi

sudo cp "${DIRECT_NYDUS_CONTAINERD_CONFIG}" "${CONTAINERD_CONFIG_BACKUP}"
patch_containerd_config "${CONTAINERD_CONFIG_BACKUP}" "${PATCHED_CONTAINERD_CONFIG}" "${SANDBOX_RUNTIME_IMAGE}" "${PATCHED_KATA_CONFIG}"
sudo cp "${PATCHED_CONTAINERD_CONFIG}" "${DIRECT_NYDUS_CONTAINERD_CONFIG}"
CONTAINERD_RESTORE_NEEDED="true"
sudo systemctl restart containerd
wait_for_containerd_ready || die "containerd did not become ready after switching to nydus"
sudo crictl info > "${CRI_INFO_AFTER_JSON}"

sed \
	-e "s/__SANDBOX_NAME__/${SANDBOX_NAME}/g" \
	-e "s/__SANDBOX_UID__/${SANDBOX_UID}/g" \
	-e "s/__NAMESPACE__/${DIRECT_NYDUS_NAMESPACE}/g" \
	"${DIRECT_NYDUS_SANDBOX_TEMPLATE}" > "${SANDBOX_CFG}"

sed \
	-e "s/__CONTAINER_NAME__/${CONTAINER_NAME}/g" \
	-e "s#__IMAGE__#${APP_RUNTIME_IMAGE}#g" \
	"${DIRECT_NYDUS_CONTAINER_TEMPLATE}" > "${CONTAINER_CFG}"

REQUEST_SENT_UTC=$(utc_timestamp)
REQUEST_SENT_LOCAL=$(local_timestamp)

cat > "${REQUEST_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "workload_type": "direct_kata_container",
  "sandbox_name": "${SANDBOX_NAME}",
  "container_name": "${CONTAINER_NAME}",
  "namespace": "${DIRECT_NYDUS_NAMESPACE}",
  "runtime_handler": "${DIRECT_NYDUS_RUNTIME_HANDLER}",
  "hypervisor": "${DIRECT_NYDUS_HYPERVISOR}",
  "source_image": "${DIRECT_NYDUS_SOURCE_IMAGE}",
  "effective_image": "${APP_RUNTIME_IMAGE}",
  "local_import_image": "${APP_EFFECTIVE_IMAGE}",
  "registry_image": "${APP_REGISTRY_IMAGE}",
  "image_conversion_mode": "converted-local-with-cri-fallback",
  "expected_snapshotter": "nydus",
  "expected_kata_config_path": "${PATCHED_KATA_CONFIG}",
  "sandbox_source_image": "${SANDBOX_SOURCE_IMAGE}",
  "sandbox_effective_image": "${SANDBOX_RUNTIME_IMAGE}",
  "sandbox_local_import_image": "${SANDBOX_EFFECTIVE_IMAGE}",
  "sandbox_registry_image": "${SANDBOX_REGISTRY_IMAGE}",
  "t_request_sent": "${REQUEST_SENT_UTC}"
}
EOF

SANDBOX_ID=$(sudo crictl runp --runtime "${DIRECT_NYDUS_RUNTIME_HANDLER}" "${SANDBOX_CFG}")
CONTAINER_ID=$(sudo crictl create "${SANDBOX_ID}" "${CONTAINER_CFG}" "${SANDBOX_CFG}")
sudo crictl start "${CONTAINER_ID}" > /dev/null
sudo crictl inspectp "${SANDBOX_ID}" > "${INSPECTP_JSON}"
sudo crictl inspect "${CONTAINER_ID}" > "${INSPECT_JSON}"

sleep "${DIRECT_NYDUS_LOG_FLUSH_WAIT_SECS}"
UNTIL_LOCAL=$(local_timestamp)

bash "${SCRIPT_DIR}/collect-logs-lite.sh" --run-dir "${RUN_DIR}" --since "${REQUEST_SENT_LOCAL}" --until "${UNTIL_LOCAL}"
python3 "${SCRIPT_DIR}/parse_direct_nydus_kata_latency.py" --run-dir "${RUN_DIR}" > /dev/null
validate_result "${RUN_DIR}"

printf "%s\n" "${RUN_DIR}"
