#!/bin/bash
set -euo pipefail

MODE="run"
REPEAT="1"
OUTPUT="/app/score.json"
PRINT_TOKENS="0"
VERBOSE="0"

usage() {
  cat <<'EOF'
Usage:
  tbench-train-bpe-tokenizer [--mode run|solve|verify|shell] [--repeat N] [--output PATH] [--print-tokens] [--verbose]

Modes:
  run     Reset input, train tokenizer, run verifier, and write score JSON.
  solve   Reset input and train tokenizer only.
  verify  Run verifier against the current /app outputs.
  shell   Start an interactive shell after resetting input.

Examples:
  docker run --rm IMAGE
  docker run --rm IMAGE --mode run --repeat 2
  docker run --rm IMAGE --mode solve --print-tokens
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
    --print-tokens)
      PRINT_TOKENS="1"
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

if ! [[ "$REPEAT" =~ ^[0-9]+$ ]] || [[ "$REPEAT" -lt 1 ]]; then
  echo "--repeat must be a positive integer" >&2
  exit 2
fi

mkdir -p /app /tests
rm -rf /app/doc
cp -a /opt/tbench/train-bpe-tokenizer/doc /app/doc
cp /opt/tbench/train-bpe-tokenizer/tokenize.py /app/tokenize.py
cp /opt/tbench/train-bpe-tokenizer/tests/test_outputs.py /tests/test_outputs.py

if [[ "$MODE" == "shell" ]]; then
  exec /bin/bash
fi

if [[ "$MODE" == "run" || "$MODE" == "solve" ]]; then
  for i in $(seq 1 "$REPEAT"); do
    rm -f /app/eng_docs.txt /app/tokens.txt /app/merges.txt /app/train.py /app/train.log "$OUTPUT"
    if [[ "$VERBOSE" == "1" ]]; then
      (cd /app && bash /opt/tbench/train-bpe-tokenizer/solution.sh)
    else
      (cd /app && bash /opt/tbench/train-bpe-tokenizer/solution.sh) > /app/train.log 2>&1
    fi
  done
fi

if [[ "$PRINT_TOKENS" == "1" && -f /app/tokens.txt ]]; then
  wc -l /app/tokens.txt /app/merges.txt
  python3 /app/tokenize.py /app/tokens.txt /app/merges.txt "Hello, world!"
fi

if [[ "$MODE" == "solve" ]]; then
  exit 0
fi

/opt/tbench/mini_pytest.py /tests/test_outputs.py | tee "$OUTPUT"
