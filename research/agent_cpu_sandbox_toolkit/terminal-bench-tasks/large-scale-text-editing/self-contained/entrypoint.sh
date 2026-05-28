#!/bin/bash
set -euo pipefail

MODE="run"
REPEAT="1"
ROWS="1000000"
OUTPUT="/app/score.json"
PRINT_HASHES="0"
VERBOSE="0"
METRICS_DIR="${TBENCH_METRICS_DIR:-}"
RUN_ID="${TBENCH_RUN_ID:-}"
TASK_ID="large-scale-text-editing"

usage() {
  cat <<'EOF'
Usage:
  tbench-large-scale-text-editing [--mode run|solve|verify|shell] [--repeat N] [--rows N] [--output PATH] [--metrics-dir PATH] [--run-id ID] [--print-hashes] [--verbose]

Modes:
  run     Generate input, create Vim macros, run verifier, and write score JSON.
  solve   Generate input and create Vim macros only.
  verify  Run verifier against current /app files.
  shell   Generate input and start an interactive shell.

Examples:
  docker run --rm IMAGE
  docker run --rm IMAGE --mode run --rows 1000000
  docker run --rm IMAGE --mode run --repeat 3 --print-hashes
  docker run --rm -v /var/lib/tbench-metrics:/metrics IMAGE --mode run --metrics-dir /metrics
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --repeat)
      REPEAT="${2:-}"
      shift 2
      ;;
    --rows)
      ROWS="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --metrics-dir)
      METRICS_DIR="${2:-}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --print-hashes)
      PRINT_HASHES="1"
      shift
      ;;
    --verbose)
      VERBOSE="1"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  run|solve|verify|shell) ;;
  *)
    echo "--mode must be one of: run, solve, verify, shell" >&2
    exit 2
    ;;
esac

for value_name in REPEAT ROWS; do
  value="${!value_name}"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [[ "$value" -lt 1 ]]; then
    echo "--${value_name,,} must be a positive integer" >&2
    exit 2
  fi
done

mkdir -p /app /tests
cp /opt/tbench/large-scale-text-editing/gen_large_csv.py /tests/gen_large_csv.py
cp /opt/tbench/large-scale-text-editing/tests/test_outputs.py /tests/test_outputs.py

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="${HOSTNAME:-container}-$$"
fi

run_solution() {
  if [[ "$VERBOSE" == "1" ]]; then
    (cd /app && bash /opt/tbench/large-scale-text-editing/solution.sh)
  else
    (cd /app && bash /opt/tbench/large-scale-text-editing/solution.sh) > /app/solution.log 2>&1
  fi
}

run_verifier() {
  (cd /app && TBENCH_TEXT_ROWS="$ROWS" /opt/tbench/mini_pytest.py /tests/test_outputs.py) | tee "$OUTPUT"
  return "${PIPESTATUS[0]}"
}

write_metric() {
  local iteration="$1"
  local status="$2"
  local exit_code="$3"

  if [[ -z "$METRICS_DIR" ]]; then
    return 0
  fi

  if ! mkdir -p "$METRICS_DIR"; then
    echo "warning: failed to create metrics dir: $METRICS_DIR" >&2
    return 0
  fi

  local safe_run_id
  local safe_host
  safe_run_id="$(printf '%s' "$RUN_ID" | tr -cs 'A-Za-z0-9_.-' '_' | cut -c1-120)"
  safe_host="$(printf '%s' "${HOSTNAME:-container}" | tr -cs 'A-Za-z0-9_.-' '_' | cut -c1-80)"
  if [[ -z "$safe_run_id" ]]; then
    safe_run_id="run"
  fi
  if [[ -z "$safe_host" ]]; then
    safe_host="container"
  fi

  local target
  local tmp
  target="$METRICS_DIR/${TASK_ID}-${safe_run_id}-${safe_host}-$$-iter$(printf '%06d' "$iteration").json"
  tmp="${target}.tmp.$$"

  if ! python3 - "$TASK_ID" "$MODE" "$ROWS" "$RUN_ID" "$iteration" \
      "$status" "$exit_code" "$OUTPUT" "${HOSTNAME:-unknown}" "$$" "$tmp" "$target" <<'PY'
import json
import os
import sys

(
    task_id,
    mode,
    rows,
    run_id,
    iteration,
    status,
    exit_code,
    output,
    hostname,
    pid,
    tmp,
    target,
) = sys.argv[1:]

event = {
    "schema_version": 1,
    "event": "task_completion",
    "task_id": task_id,
    "mode": mode,
    "rows": int(rows),
    "run_id": run_id,
    "iteration": int(iteration),
    "status": status,
    "exit_code": int(exit_code),
    "hostname": hostname,
    "pid": int(pid),
    "output": output,
}
with open(tmp, "w", encoding="utf-8") as f:
    f.write(json.dumps(event, sort_keys=True) + "\n")
os.replace(tmp, target)
PY
  then
    echo "warning: failed to write task metric to: $METRICS_DIR" >&2
  fi
}

generate_input() {
  rm -f /app/input.csv /app/expected.csv
  (cd /app && TBENCH_TEXT_ROWS="$ROWS" python3 /tests/gen_large_csv.py input)
}

if [[ "$MODE" == "shell" ]]; then
  generate_input
  exec /bin/bash
fi

if [[ "$MODE" == "run" || "$MODE" == "solve" ]]; then
  overall_status=0
  for i in $(seq 1 "$REPEAT"); do
    rm -f /app/apply_macros.vim /app/_defs_only.vim /app/vim_keystrokes.out /app/vim_regs.out "$OUTPUT"

    set +e
    generate_input
    step_status="$?"
    if [[ "$step_status" -eq 0 ]]; then
      run_solution
      step_status="$?"
    fi
    if [[ "$step_status" -eq 0 && "$MODE" == "run" ]]; then
      run_verifier
      step_status="$?"
    fi
    set -e

    if [[ "$step_status" -eq 0 ]]; then
      write_metric "$i" "pass" 0
    else
      write_metric "$i" "fail" "$step_status"
      overall_status="$step_status"
      break
    fi
  done
  if [[ "$overall_status" -ne 0 ]]; then
    exit "$overall_status"
  fi
else
  set +e
  run_verifier
  step_status="$?"
  set -e
  if [[ "$step_status" -eq 0 ]]; then
    write_metric 1 "pass" 0
  else
    write_metric 1 "fail" "$step_status"
    exit "$step_status"
  fi
fi

if [[ "$PRINT_HASHES" == "1" ]]; then
  sha256sum /app/input.csv /app/expected.csv 2>/dev/null || true
fi
