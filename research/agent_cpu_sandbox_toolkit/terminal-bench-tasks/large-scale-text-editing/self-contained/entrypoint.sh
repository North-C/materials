#!/bin/bash
set -euo pipefail

MODE="run"
REPEAT="1"
ROWS="1000000"
OUTPUT="/app/score.json"
PRINT_HASHES="0"
VERBOSE="0"

usage() {
  cat <<'EOF'
Usage:
  tbench-large-scale-text-editing [--mode run|solve|verify|shell] [--repeat N] [--rows N] [--output PATH] [--print-hashes] [--verbose]

Modes:
  run     Generate input, create Vim macros, run verifier, and write score JSON.
  solve   Generate input and create Vim macros only.
  verify  Run verifier against current /app files.
  shell   Generate input and start an interactive shell.

Examples:
  docker run --rm IMAGE
  docker run --rm IMAGE --mode run --rows 1000000
  docker run --rm IMAGE --mode run --repeat 3 --print-hashes
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

generate_input() {
  rm -f /app/input.csv /app/expected.csv
  (cd /app && TBENCH_TEXT_ROWS="$ROWS" python3 /tests/gen_large_csv.py input)
}

if [[ "$MODE" == "shell" ]]; then
  generate_input
  exec /bin/bash
fi

if [[ "$MODE" == "run" || "$MODE" == "solve" ]]; then
  for i in $(seq 1 "$REPEAT"); do
    rm -f /app/apply_macros.vim /app/_defs_only.vim /app/vim_keystrokes.out /app/vim_regs.out "$OUTPUT"
    generate_input
    if [[ "$VERBOSE" == "1" ]]; then
      (cd /app && bash /opt/tbench/large-scale-text-editing/solution.sh)
    else
      (cd /app && bash /opt/tbench/large-scale-text-editing/solution.sh) > /app/solution.log 2>&1
    fi
    if [[ "$MODE" == "run" ]]; then
      (cd /app && TBENCH_TEXT_ROWS="$ROWS" /opt/tbench/mini_pytest.py /tests/test_outputs.py) | tee "$OUTPUT"
    fi
  done
else
  (cd /app && TBENCH_TEXT_ROWS="$ROWS" /opt/tbench/mini_pytest.py /tests/test_outputs.py) | tee "$OUTPUT"
fi

if [[ "$PRINT_HASHES" == "1" ]]; then
  sha256sum /app/input.csv /app/expected.csv 2>/dev/null || true
fi
