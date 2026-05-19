#!/bin/bash
set -euo pipefail

MODE="run"
REPEAT="1"
OUTPUT="/app/score.json"
PRINT_REPORT="0"

usage() {
  cat <<'EOF'
Usage:
  tbench-analyze-access-logs [--mode run|solve|verify|shell] [--repeat N] [--output PATH] [--print-report]

Modes:
  run     Reset input, run solution, run verifier, and write score JSON.
  solve   Reset input and run solution only.
  verify  Run verifier against the current /app/report.txt.
  shell   Start an interactive shell after resetting input.

Examples:
  docker run --rm IMAGE
  docker run --rm IMAGE --mode run --repeat 5
  docker run --rm IMAGE --mode solve --print-report
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
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --print-report)
      PRINT_REPORT="1"
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

if ! [[ "$REPEAT" =~ ^[0-9]+$ ]] || [[ "$REPEAT" -lt 1 ]]; then
  echo "--repeat must be a positive integer" >&2
  exit 2
fi

mkdir -p /app /tests
cp /opt/tbench/analyze-access-logs/access_log /app/access_log
cp /opt/tbench/analyze-access-logs/tests/test_outputs.py /tests/test_outputs.py

if [[ "$MODE" == "shell" ]]; then
  exec /bin/bash
fi

if [[ "$MODE" == "run" || "$MODE" == "solve" ]]; then
  for i in $(seq 1 "$REPEAT"); do
    rm -f /app/report.txt "$OUTPUT"
    bash /opt/tbench/analyze-access-logs/solution.sh
  done
fi

if [[ "$PRINT_REPORT" == "1" && -f /app/report.txt ]]; then
  cat /app/report.txt
fi

if [[ "$MODE" == "solve" ]]; then
  exit 0
fi

/opt/tbench/mini_pytest.py /tests/test_outputs.py | tee "$OUTPUT"
