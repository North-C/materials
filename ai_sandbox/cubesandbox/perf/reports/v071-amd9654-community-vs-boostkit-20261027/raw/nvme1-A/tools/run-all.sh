#!/usr/bin/env bash
# Community 31d911e4 components (A2 swap, dirty_log removed) on the nvme1 XFS deployment: same matrix as the 10-27 A1/B campaign.
# core list (minus density and c100) -> c100 warmup + 5 -> pause-c100 extension.
set -euo pipefail
B=/path/to/workdir
R=$B/nvme1-A-20261027
O=$R/results
cd "$B"
source "$R/tools/test-env.sh"
API_LOG=/data/log/CubeAPI/cube-api-$(date +%F).log
mkdir -p "$O/gates"
python3 tools/host-conditions.py "$O/conditions-before-measurements.json"
printf 'case\tstart_utc\tend_utc\tapi_log\tapi_off_start\tapi_off_end\trc\n' > "$O/windows.tsv"

one() {  # one <case> <run-dir-name> <native command...>
  local name=$1 dir=$2; shift 2
  sleep 15
  bash "$R/tools/wait-clean.sh" "$O/gates/$dir-before"
  local s e o1 o2 rc=0
  s=$(date -u +%FT%T.%NZ); o1=$(stat -c %s "$API_LOG")
  "$@" >"$O/$dir-entry.log" 2>&1 || rc=$?
  e=$(date -u +%FT%T.%NZ); o2=$(stat -c %s "$API_LOG")
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$s" "$e" "$API_LOG" "$o1" "$o2" "$rc" >> "$O/windows.tsv"
  printf '%s %s rc=%s\n' "$e" "$dir" "$rc"
  if [[ -d $O/$dir ]]; then tail -n 4 "$O/$dir/stdout.log" || true; python3 tools/cleanup-owned.py "$O/$dir"; fi
  [[ $rc == 0 ]] || { echo "failed $dir rc=$rc"; exit "$rc"; }
}
native() { CPB_RUN_DIR=$O/$2 bash cube-perf-bench/scripts/community-native.sh run "$1" --authorize-run --exclusive-template; }

while IFS= read -r c; do
  [[ $c != density* && $c != extended-startup-c100n100 ]] || continue
  one "$c" "$c" native "$c" "$c"
done < <(bash cube-perf-bench/scripts/community-native.sh list)

for r in warmup 1 2 3 4 5; do
  one extended-startup-c100n100 "c100-$r" native extended-startup-c100n100 "c100-$r"
  jq -c '{summary,create}' "$O/c100-$r/cube-bench.json"
done

pause100() {
  local out=$O/extended-pause-c100
  mkdir "$out"
  bash cube-perf-bench/scripts/community-native.sh check pause-c10 >"$out/prerequisites.log" 2>&1
  printf 'case=extended-pause-c100 profile=extended source_ref=%s\n' "$CPB_UPSTREAM_REF" >"$out/invocation.txt"
  printf '%q ' "$CPB_PYTHON" -E -s -B "$CPB_UPSTREAM_DIR/examples/snapshot-rollback-clone/bench_pause_resume_concurrency.py" -c 100 -n 5 >>"$out/invocation.txt"
  printf '\nSeparate extension; same prerequisites as native pause-c10; not a CPB built-in case.\n' >>"$out/invocation.txt"
  local rc=0
  "$CPB_PYTHON" -E -s -B "$CPB_UPSTREAM_DIR/examples/snapshot-rollback-clone/bench_pause_resume_concurrency.py" -c 100 -n 5 >"$out/stdout.log" 2>"$out/stderr.log" || rc=$?
  echo "$rc" >"$out/exit-code"
  return "$rc"
}
one extended-pause-c100 extended-pause-c100 pause100

sleep 15
bash "$R/tools/wait-clean.sh" "$O/gates/matrix-after"
python3 tools/host-conditions.py "$O/conditions-after-measurements.json"
echo "ALL DONE $(date -u +%FT%TZ)"
