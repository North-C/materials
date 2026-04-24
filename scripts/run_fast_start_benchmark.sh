#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
BENCH_DIR="${REPO_ROOT}/CubeAPI/benchmark"
BENCH_BIN="${BENCH_DIR}/cube-bench"
DETAILED_ANALYZER="${REPO_ROOT}/dev-env/measure_startup_detailed.py"

API_URL="${E2B_API_URL:-http://127.0.0.1:3000}"
API_KEY="${E2B_API_KEY:-dummy}"
TEMPLATE_ID="${CUBE_TEMPLATE_ID:-}"
OUT_DIR=""

SINGLE_CONCURRENCY=1
SINGLE_TOTAL=100
SINGLE_WARMUP=5

HIGH_CONCURRENCY=50
HIGH_TOTAL=500
HIGH_WARMUP=10

DETAILED_ROUNDS=20
RUN_DETAILED=1

log() {
  printf '[fast-start-bench] %s\n' "$*"
}

warn() {
  printf '[fast-start-bench] WARN: %s\n' "$*" >&2
}

die() {
  printf '[fast-start-bench] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  dev-env/run_fast_start_benchmark.sh [options]

Options:
  --template-id ID           Template ID to benchmark. Falls back to CUBE_TEMPLATE_ID.
  --api-url URL              CubeAPI base URL. Falls back to E2B_API_URL or http://127.0.0.1:3000.
  --api-key KEY              API key. Falls back to E2B_API_KEY or dummy.
  --out-dir DIR              Output directory for artifacts.
  --single-concurrency N     Concurrency for the single-latency pass. Default: 1.
  --single-total N           Total requests for the single-latency pass. Default: 100.
  --single-warmup N          Warmup rounds for the single-latency pass. Default: 5.
  --high-concurrency N       Concurrency for the stress pass. Default: 50.
  --high-total N             Total requests for the stress pass. Default: 500.
  --high-warmup N            Warmup rounds for the stress pass. Default: 10.
  --detailed-rounds N        Rounds for the detailed analyzer. Default: 20.
  --skip-detailed            Skip the detailed server-side analyzer.
  -h, --help                 Show this help text.

Environment:
  CUBE_TEMPLATE_ID
  E2B_API_URL
  E2B_API_KEY

What this runs:
  1. CubeAPI/benchmark/cube-bench in create-only mode with c=1
  2. CubeAPI/benchmark/cube-bench in create-only mode with c=50
  3. Optional dev-env/measure_startup_detailed.py if present

Reference README targets:
  - c=1 average around 60ms
  - c=50 average around 67ms, p95 around 90ms, p99 around 137ms
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-id)
      TEMPLATE_ID="${2:?missing value for --template-id}"
      shift 2
      ;;
    --api-url)
      API_URL="${2:?missing value for --api-url}"
      shift 2
      ;;
    --api-key)
      API_KEY="${2:?missing value for --api-key}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:?missing value for --out-dir}"
      shift 2
      ;;
    --single-concurrency)
      SINGLE_CONCURRENCY="${2:?missing value for --single-concurrency}"
      shift 2
      ;;
    --single-total)
      SINGLE_TOTAL="${2:?missing value for --single-total}"
      shift 2
      ;;
    --single-warmup)
      SINGLE_WARMUP="${2:?missing value for --single-warmup}"
      shift 2
      ;;
    --high-concurrency)
      HIGH_CONCURRENCY="${2:?missing value for --high-concurrency}"
      shift 2
      ;;
    --high-total)
      HIGH_TOTAL="${2:?missing value for --high-total}"
      shift 2
      ;;
    --high-warmup)
      HIGH_WARMUP="${2:?missing value for --high-warmup}"
      shift 2
      ;;
    --detailed-rounds)
      DETAILED_ROUNDS="${2:?missing value for --detailed-rounds}"
      shift 2
      ;;
    --skip-detailed)
      RUN_DETAILED=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "${TEMPLATE_ID}" ]] || die "template id is required. Pass --template-id or set CUBE_TEMPLATE_ID."

if [[ -z "${OUT_DIR}" ]]; then
  OUT_DIR="${REPO_ROOT}/benchmark-artifacts/fast-start-$(date +%Y%m%d-%H%M%S)"
fi

mkdir -p "${OUT_DIR}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

require_cmd go
require_cmd python3

check_local_environment() {
  if [[ "${API_URL}" == "http://127.0.0.1:3000" || "${API_URL}" == "http://localhost:3000" ]]; then
    if [[ ! -e /dev/kvm ]]; then
      warn "/dev/kvm is missing. The README latency target was measured on a KVM-capable host."
    fi
  fi

  if command -v systemd-detect-virt >/dev/null 2>&1; then
    local virt_kind
    virt_kind="$(systemd-detect-virt 2>/dev/null || true)"
    if [[ -n "${virt_kind}" && "${virt_kind}" != "none" ]]; then
      warn "systemd-detect-virt reports '${virt_kind}'. The README 60ms number was documented for bare metal."
    fi
  fi
}

check_api_health() {
  python3 - "${API_URL}" <<'PY'
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
url = base + "/health"

with urllib.request.urlopen(url, timeout=5) as resp:
    body = resp.read(256).decode("utf-8", "replace").strip()
    print(f"[fast-start-bench] API health OK: {resp.status} {url} {body}")
PY
}

write_metadata() {
  cat > "${OUT_DIR}/metadata.txt" <<EOF
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
repo_root=${REPO_ROOT}
api_url=${API_URL}
template_id=${TEMPLATE_ID}
single_concurrency=${SINGLE_CONCURRENCY}
single_total=${SINGLE_TOTAL}
single_warmup=${SINGLE_WARMUP}
high_concurrency=${HIGH_CONCURRENCY}
high_total=${HIGH_TOTAL}
high_warmup=${HIGH_WARMUP}
detailed_rounds=${DETAILED_ROUNDS}
run_detailed=${RUN_DETAILED}
hostname=$(hostname)
EOF
}

build_benchmark() {
  log "Building cube-bench in ${BENCH_DIR}"
  (
    cd "${BENCH_DIR}"
    go build -o cube-bench .
  )
}

summarize_json() {
  local scenario="$1"
  local json_path="$2"
  python3 - "${scenario}" "${json_path}" <<'PY'
import json
import sys

scenario = sys.argv[1]
path = sys.argv[2]

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

create = data.get("create") or {}
summary = data.get("summary") or {}

def fmt(value):
    if value is None:
        return "n/a"
    return f"{value:.1f}"

def pass_fail(ok):
    return "PASS" if ok else "FAIL"

avg = create.get("avg")
p95 = create.get("p95")
p99 = create.get("p99")
success_rate = summary.get("success_rate")
throughput = summary.get("throughput_qps")

print(f"[fast-start-bench] Summary for {scenario}")
print(f"[fast-start-bench]   avg={fmt(avg)}ms p95={fmt(p95)}ms p99={fmt(p99)}ms success_rate={fmt(success_rate * 100 if success_rate is not None else None)}% throughput={fmt(throughput)} qps")

if scenario == "single":
    target_avg = 60.0
    if avg is not None:
        print(f"[fast-start-bench]   README comparison: {pass_fail(avg <= target_avg)} (avg <= {target_avg:.0f}ms)")
elif scenario == "c50":
    target_avg = 67.0
    target_p95 = 90.0
    target_p99 = 137.0
    avg_ok = avg is not None and avg <= target_avg
    p95_ok = p95 is not None and p95 <= target_p95
    p99_ok = p99 is not None and p99 <= target_p99
    print(f"[fast-start-bench]   README comparison: {pass_fail(avg_ok and p95_ok and p99_ok)} (avg <= {target_avg:.0f}ms, p95 <= {target_p95:.0f}ms, p99 <= {target_p99:.0f}ms)")
PY
}

run_bench() {
  local scenario="$1"
  local concurrency="$2"
  local total="$3"
  local warmup="$4"
  local json_path="${OUT_DIR}/${scenario}.json"
  local log_path="${OUT_DIR}/${scenario}.log"

  log "Running ${scenario}: concurrency=${concurrency} total=${total} warmup=${warmup}"
  (
    cd "${BENCH_DIR}"
    "${BENCH_BIN}" \
      --no-tui \
      -c "${concurrency}" \
      -n "${total}" \
      -w "${warmup}" \
      -m create-only \
      --api-url "${API_URL}" \
      --api-key "${API_KEY}" \
      -t "${TEMPLATE_ID}" \
      -o "${json_path}"
  ) | tee "${log_path}"

  summarize_json "${scenario}" "${json_path}" | tee -a "${OUT_DIR}/summary.txt"
}

run_detailed_analyzer() {
  if [[ "${RUN_DETAILED}" -ne 1 ]]; then
    log "Skipping detailed analyzer by request"
    return 0
  fi

  if [[ ! -f "${DETAILED_ANALYZER}" ]]; then
    warn "Detailed analyzer not found at ${DETAILED_ANALYZER}; skipping"
    return 0
  fi

  log "Running detailed analyzer for ${DETAILED_ROUNDS} rounds"
  if ! python3 "${DETAILED_ANALYZER}" "${TEMPLATE_ID}" "${DETAILED_ROUNDS}" | tee "${OUT_DIR}/detailed.log"; then
    warn "Detailed analyzer failed; benchmark JSON artifacts are still available"
  fi
}

check_local_environment
check_api_health
write_metadata
build_benchmark

{
  echo "[fast-start-bench] Output directory: ${OUT_DIR}"
  echo "[fast-start-bench] API URL: ${API_URL}"
  echo "[fast-start-bench] Template ID: ${TEMPLATE_ID}"
  echo "[fast-start-bench] Reference target: c=1 avg around 60ms"
  echo "[fast-start-bench] Reference target: c=50 avg around 67ms, p95 around 90ms, p99 around 137ms"
} | tee "${OUT_DIR}/summary.txt"

run_bench "single" "${SINGLE_CONCURRENCY}" "${SINGLE_TOTAL}" "${SINGLE_WARMUP}"
run_bench "c50" "${HIGH_CONCURRENCY}" "${HIGH_TOTAL}" "${HIGH_WARMUP}"
run_detailed_analyzer

log "Benchmark complete. Artifacts saved in ${OUT_DIR}"
