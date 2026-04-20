#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../../.." && pwd)

RESULTS_ROOT="${RESULTS_ROOT:-${REPO_ROOT}/results-direct-nydus-lite}"
WARMUP_COUNT="${WARMUP_COUNT:-1}"
SAMPLE_COUNT="${SAMPLE_COUNT:-5}"
BATCH_ID="${BATCH_ID:-batch-$(date -u +%Y%m%dT%H%M%SZ)}"
DIRECT_NYDUS_RUN_SAMPLE_RETRIES="${DIRECT_NYDUS_RUN_SAMPLE_RETRIES:-1}"
DIRECT_NYDUS_RUN_SAMPLE_SCRIPT="${DIRECT_NYDUS_RUN_SAMPLE_SCRIPT:-${SCRIPT_DIR}/run-direct-cri-nydus-lite.sh}"
DIRECT_NYDUS_AGGREGATE_BATCH_RESULTS_SCRIPT="${DIRECT_NYDUS_AGGREGATE_BATCH_RESULTS_SCRIPT:-${SCRIPT_DIR}/aggregate_batch_results.py}"

die() {
	echo "[$(basename "$0")] ERROR: $*" >&2
	exit 1
}

required_cmds() {
	local cmd
	for cmd in "$@"; do
		command -v "${cmd}" > /dev/null 2>&1 || die "command not available: ${cmd}"
	done
}

utc_timestamp() {
	date -u +"%Y-%m-%dT%H:%M:%SZ"
}

create_batch_dir() {
	local batch_id="$1"
	local batch_dir="${RESULTS_ROOT}/$(date -u +%F)/${batch_id}"
	mkdir -p "${batch_dir}/raw" "${batch_dir}/summary"
	printf "%s\n" "${batch_dir}"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--warmup-count)
			WARMUP_COUNT="$2"
			shift 2
			;;
		--sample-count)
			SAMPLE_COUNT="$2"
			shift 2
			;;
		--batch-id)
			BATCH_ID="$2"
			shift 2
			;;
		*)
			die "unknown argument: $1"
			;;
	esac
done

[[ "${WARMUP_COUNT}" =~ ^[0-9]+$ ]] || die "warmup count must be a non-negative integer"
[[ "${SAMPLE_COUNT}" =~ ^[0-9]+$ ]] || die "sample count must be a non-negative integer"
[[ "${DIRECT_NYDUS_RUN_SAMPLE_RETRIES}" =~ ^[0-9]+$ ]] || die "retry count must be a non-negative integer"

required_cmds bash python3

BATCH_DIR=$(create_batch_dir "${BATCH_ID}")
WARMUP_RUNS_FILE="${BATCH_DIR}/raw/warmup-run-dirs.txt"
SAMPLE_RUNS_FILE="${BATCH_DIR}/raw/sample-run-dirs.txt"
FAILED_ATTEMPTS_FILE="${BATCH_DIR}/raw/failed-attempts.log"

: > "${WARMUP_RUNS_FILE}"
: > "${SAMPLE_RUNS_FILE}"
: > "${FAILED_ATTEMPTS_FILE}"
: > "${BATCH_DIR}/raw/warmup-attempts.log"
: > "${BATCH_DIR}/raw/sample-attempts.log"

warmup_run_dirs=()
sample_run_dirs=()
failed_attempt_count=0
RUN_SERIES_ITEM_RESULT=""

run_series_item() {
	local phase="$1"
	local index="$2"
	local attempts=0
	local max_attempts=$((DIRECT_NYDUS_RUN_SAMPLE_RETRIES + 1))
	local run_dir=""

	while (( attempts < max_attempts )); do
		attempts=$((attempts + 1))
		if run_dir=$(bash "${DIRECT_NYDUS_RUN_SAMPLE_SCRIPT}" 2>> "${FAILED_ATTEMPTS_FILE}"); then
			printf "%s attempt=%s index=%s run_dir=%s\n" "${phase}" "${attempts}" "${index}" "${run_dir}" >> "${BATCH_DIR}/raw/${phase}-attempts.log"
			RUN_SERIES_ITEM_RESULT="${run_dir}"
			return 0
		fi
		failed_attempt_count=$((failed_attempt_count + 1))
		printf "%s attempt=%s index=%s status=failed\n" "${phase}" "${attempts}" "${index}" >> "${FAILED_ATTEMPTS_FILE}"
	done

	return 1
}

for ((i = 0; i < WARMUP_COUNT; i++)); do
	if run_series_item warmup "${i}"; then
		run_dir="${RUN_SERIES_ITEM_RESULT}"
		warmup_run_dirs+=("${run_dir}")
		printf "%s\n" "${run_dir}" >> "${WARMUP_RUNS_FILE}"
	fi
done

for ((i = 0; i < SAMPLE_COUNT; i++)); do
	if run_series_item sample "${i}"; then
		run_dir="${RUN_SERIES_ITEM_RESULT}"
		sample_run_dirs+=("${run_dir}")
		printf "%s\n" "${run_dir}" >> "${SAMPLE_RUNS_FILE}"
	fi
done

aggregate_args=(--batch-dir "${BATCH_DIR}")
for run_dir in "${warmup_run_dirs[@]}"; do
	aggregate_args+=(--warmup-run-dir "${run_dir}")
done
for run_dir in "${sample_run_dirs[@]}"; do
	aggregate_args+=(--sample-run-dir "${run_dir}")
done

python3 "${DIRECT_NYDUS_AGGREGATE_BATCH_RESULTS_SCRIPT}" "${aggregate_args[@]}" > /dev/null

cat > "${BATCH_DIR}/summary/batch-meta.json" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "created_at": "$(utc_timestamp)",
  "warmup_count": ${WARMUP_COUNT},
  "sample_count": ${SAMPLE_COUNT},
  "successful_warmup_count": ${#warmup_run_dirs[@]},
  "successful_sample_count": ${#sample_run_dirs[@]},
  "requested_sample_count": ${SAMPLE_COUNT},
  "failed_attempt_count": ${failed_attempt_count},
  "retry_count_per_run": ${DIRECT_NYDUS_RUN_SAMPLE_RETRIES}
}
EOF

printf "%s\n" "${BATCH_DIR}"
