#!/bin/bash
set -euo pipefail

MODE="run"
REPEAT="1"
ROWS="1000000"
PRINT_HASHES="0"
VERBOSE="0"
METRICS_DIR="${TBENCH_METRICS_DIR:-}"
RUN_ID="${TBENCH_RUN_ID:-}"
PROFILE_FILE="${TBENCH_PROFILE_FILE:-}"
PROFILE_DIR="${TBENCH_PROFILE_DIR:-}"
TASK_ID="large-scale-text-editing"
CURRENT_ITERATION="1"
WORK_DIR="${TBENCH_WORK_DIR:-/tmp/tbench-work}"
TEST_DIR="${TBENCH_TEST_DIR:-/tmp/tbench-tests}"
OUTPUT="${TBENCH_OUTPUT:-$WORK_DIR/score.json}"
export PYTHONPATH="/opt/tbench:${PYTHONPATH:-}"

usage() {
  cat <<'EOF'
Usage:
  tbench-large-scale-text-editing [--mode run|solve|verify|shell] [--repeat N] [--rows N] [--output PATH] [--metrics-dir PATH] [--run-id ID] [--profile-file PATH] [--profile-dir PATH] [--print-hashes] [--verbose]

Modes:
  run     Generate input, create Vim macros, run verifier, and write score JSON.
  solve   Generate input and create Vim macros only.
  verify  Run verifier against current task work directory files.
  shell   Generate input and start an interactive shell.

Examples:
  docker run --rm IMAGE
  docker run --rm IMAGE --mode run --rows 1000000
  docker run --rm IMAGE --mode run --repeat 3 --print-hashes
  docker run --rm -v /var/lib/tbench-metrics:/metrics IMAGE --mode run --metrics-dir /metrics
  tbench-large-scale-text-editing --mode run --rows 1000000 --profile-file /tmp/tbench-profile.jsonl

Environment:
  TBENCH_WORK_DIR  Directory for task files such as input.csv and score.json. Default: /tmp/tbench-work
  TBENCH_TEST_DIR  Directory for copied test helpers. Default: /tmp/tbench-tests
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
    --profile-file)
      PROFILE_FILE="${2:-}"
      shift 2
      ;;
    --profile-dir)
      PROFILE_DIR="${2:-}"
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

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="${HOSTNAME:-container}-$$"
fi

sanitize_label() {
  local value="$1"
  local fallback="$2"
  local limit="$3"
  local safe
  safe="$(printf '%s' "$value" | tr -cs 'A-Za-z0-9_.-' '_' | cut -c1-"$limit")"
  if [[ -z "$safe" ]]; then
    safe="$fallback"
  fi
  printf '%s' "$safe"
}

epoch_ns() {
  local value="${EPOCHREALTIME:-}"
  if [[ "$value" == *.* ]]; then
    local sec="${value%.*}"
    local frac="${value#*.}000000"
    printf '%s%s000\n' "$sec" "${frac:0:6}"
  else
    date +%s%N
  fi
}

init_profile() {
  if [[ -z "$PROFILE_FILE" && -z "$PROFILE_DIR" ]]; then
    return 0
  fi

  if [[ -z "$PROFILE_FILE" ]]; then
    local safe_run_id
    local safe_host
    safe_run_id="$(sanitize_label "$RUN_ID" "run" 120)"
    safe_host="$(sanitize_label "${HOSTNAME:-container}" "container" 80)"
    PROFILE_FILE="$PROFILE_DIR/${TASK_ID}-${safe_run_id}-${safe_host}-$$.profile.jsonl"
  fi

  if ! mkdir -p "$(dirname "$PROFILE_FILE")"; then
    echo "warning: failed to create profile dir for: $PROFILE_FILE" >&2
    PROFILE_FILE=""
    return 0
  fi
  if ! : > "$PROFILE_FILE"; then
    echo "warning: failed to initialize profile file: $PROFILE_FILE" >&2
    PROFILE_FILE=""
    return 0
  fi

  export TBENCH_PROFILE_FILE="$PROFILE_FILE"
  export TBENCH_PROFILE_TASK_ID="$TASK_ID"
  export TBENCH_PROFILE_MODE="$MODE"
  export TBENCH_PROFILE_ROWS="$ROWS"
  export TBENCH_PROFILE_RUN_ID="$RUN_ID"
}

write_profile_stage() {
  local iteration="$1"
  local stage="$2"
  local phase="$3"
  local resource_type="$4"
  local resource_object="$5"
  local status="$6"
  local exit_code="$7"
  local started_ns="$8"
  local finished_ns="$9"

  if [[ -z "$PROFILE_FILE" ]]; then
    return 0
  fi

  TBENCH_PROFILE_ITERATION="$iteration" \
    /opt/tbench/profile_event.py \
    "$stage" "$phase" "$resource_type" "$resource_object" \
    "$status" "$exit_code" "$started_ns" "$finished_ns" \
    || echo "warning: failed to write profile stage to: $PROFILE_FILE" >&2
}

time_stage() {
  local iteration="$1"
  local stage="$2"
  local phase="$3"
  local resource_type="$4"
  local resource_object="$5"
  shift 5

  local old_opts="$-"
  local started_ns=""
  local finished_ns=""
  local rc=0
  local status="pass"

  if [[ -n "$PROFILE_FILE" ]]; then
    started_ns="$(epoch_ns)"
  fi

  set +e
  "$@"
  rc="$?"
  case "$old_opts" in
    *e*) set -e ;;
    *) set +e ;;
  esac

  if [[ -n "$PROFILE_FILE" ]]; then
    finished_ns="$(epoch_ns)"
    if [[ "$rc" -ne 0 ]]; then
      status="fail"
    fi
    write_profile_stage "$iteration" "$stage" "$phase" "$resource_type" "$resource_object" \
      "$status" "$rc" "$started_ns" "$finished_ns"
  fi

  return "$rc"
}

prepare_environment() {
  mkdir -p "$WORK_DIR" "$TEST_DIR"
  cp /opt/tbench/large-scale-text-editing/gen_large_csv.py "$TEST_DIR/gen_large_csv.py"
  cp /opt/tbench/large-scale-text-editing/tests/test_outputs.py "$TEST_DIR/test_outputs.py"
}

run_solution() {
  if [[ "$VERBOSE" == "1" ]]; then
    (cd "$WORK_DIR" && bash /opt/tbench/large-scale-text-editing/solution.sh)
  else
    (cd "$WORK_DIR" && bash /opt/tbench/large-scale-text-editing/solution.sh) > "$WORK_DIR/solution.log" 2>&1
  fi
}

run_verifier() {
  (cd "$WORK_DIR" && TBENCH_TEXT_ROWS="$ROWS" TBENCH_WORK_DIR="$WORK_DIR" TBENCH_TEST_DIR="$TEST_DIR" TBENCH_PROFILE_ITERATION="$CURRENT_ITERATION" /opt/tbench/mini_pytest.py "$TEST_DIR/test_outputs.py") | tee "$OUTPUT"
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
  rm -f "$WORK_DIR/input.csv" "$WORK_DIR/expected.csv"
  (cd "$WORK_DIR" && TBENCH_TEXT_ROWS="$ROWS" python3 "$TEST_DIR/gen_large_csv.py" input)
}

init_profile
set +e
time_stage 0 "entrypoint.prepare_environment" "setup" "filesystem" "$WORK_DIR,$TEST_DIR" prepare_environment
prepare_status="$?"
set -e
if [[ "$prepare_status" -ne 0 ]]; then
  exit "$prepare_status"
fi

if [[ "$MODE" == "shell" ]]; then
  CURRENT_ITERATION="1"
  export TBENCH_PROFILE_ITERATION="$CURRENT_ITERATION"
  time_stage 1 "entrypoint.generate_input" "input_generation" "csv_file" "$WORK_DIR/input.csv" generate_input
  exec /bin/bash
fi

if [[ "$MODE" == "run" || "$MODE" == "solve" ]]; then
  overall_status=0
  for i in $(seq 1 "$REPEAT"); do
    rm -f "$WORK_DIR/apply_macros.vim" "$WORK_DIR/_defs_only.vim" "$WORK_DIR/vim_keystrokes.out" "$WORK_DIR/vim_regs.out" "$OUTPUT"
    CURRENT_ITERATION="$i"
    export TBENCH_PROFILE_ITERATION="$CURRENT_ITERATION"

    set +e
    time_stage "$i" "entrypoint.generate_input" "input_generation" "csv_file" "$WORK_DIR/input.csv" generate_input
    step_status="$?"
    if [[ "$step_status" -eq 0 ]]; then
      time_stage "$i" "entrypoint.generate_solution_macro" "solution_generation" "vim_script" "$WORK_DIR/apply_macros.vim" run_solution
      step_status="$?"
    fi
    if [[ "$step_status" -eq 0 && "$MODE" == "run" ]]; then
      time_stage "$i" "entrypoint.verify_total" "verification" "test_suite" "$TEST_DIR/test_outputs.py" run_verifier
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
  CURRENT_ITERATION="1"
  export TBENCH_PROFILE_ITERATION="$CURRENT_ITERATION"
  set +e
  time_stage 1 "entrypoint.verify_total" "verification" "test_suite" "$TEST_DIR/test_outputs.py" run_verifier
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
  sha256sum "$WORK_DIR/input.csv" "$WORK_DIR/expected.csv" 2>/dev/null || true
fi
