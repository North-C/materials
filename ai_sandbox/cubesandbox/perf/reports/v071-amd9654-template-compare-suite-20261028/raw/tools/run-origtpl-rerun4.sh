#!/usr/bin/env bash
# 21:52 CST: rerun the 4 items whose CubeAPI windows in results-origtpl-rest-2115 contained another user's creates
# (create-c50, clone-c10n100, clone-c50n100, extended-startup-c200n200). Otherwise identical to run-origtpl-rest.sh.
# Original header: 21:15 CST user: run every remaining cube-perf-bench item one by one on the rebuilt original template
# (tpl-4feed5ee..., same request as 10-27 tpl-3d73a659: 2048Mi, 1G writable, probe /health 500 ms).
# One native invocation per item (same as the 10-27 matrix), runner list order. Skips items already measured on
# this template (startup-c50n500, snapshot-c10, extended-startup-c100n100) and manual density; adds the
# extended pause-c100 used in the 10-27 matrix. A failed item is recorded and the run continues.
# /snapshots is saved before/after each item; snapshots of other users are never deleted.
# 21:21 first launch stopped at the first gate (another user's 10-instance hold test); gate refusals now wait
# for quiet (3 consecutive 10 s checks) and retry instead of exiting.
# Components as deployed by user-b at 19:10 CST; same per-item gate and cleanup as run-origtpl.sh.
set -euo pipefail
B=/path/to/workdir
R=$B/nvme1-peertpl-20261028
O=$R/results-origtpl-rerun4-2152
cd "$B"
source "$R/tools/test-env-origtpl.sh"
API_LOG=$(ls -t /data/log/CubeAPI/cube-api-*.log | head -1)
mkdir -p "$O/gates" "$O/snapshots"
printf 'case\tstart_utc\tend_utc\tapi_log\tapi_off_start\tapi_off_end\trc\n' > "$O/windows.tsv"
printf 'case\tstart_utc\tend_utc\tload1_before\thost_busy_pct\thugepages_free\n' > "$O/host-load.tsv"

busy() { awk '/^cpu /{print $2+$3+$4+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }
quiet() {  # no other Cube benchmark process, empty inventory, load1 <= 4
  local b n l
  b=$(pgrep -fc '[c]reate_bench|[p]ause_resume_bench|[c]ube-bench |[h]old_n.py' || true)
  n=$(curl -s -m 10 http://127.0.0.1:3000/sandboxes | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo err)
  l=$(cut -d' ' -f1 /proc/loadavg)
  [[ $b == 0 && $n == 0 ]] && awk -v l="$l" 'BEGIN{exit !(l<=4)}'
}
gate() {  # gate <dir>: wait-clean; if another user's test holds the host, wait for quiet and retry (max 6 h)
  local t ok
  for t in $(seq 1 36); do
    bash "$R/tools/wait-clean.sh" "$O/gates/$1-before-try$t" && return 0
    echo "$(date -u +%FT%TZ) gate refused before $1 (try $t); waiting for the host to be quiet"
    ok=0
    for _ in $(seq 1 60); do
      if quiet; then ok=$((ok+1)); else ok=0; fi
      (( ok >= 3 )) && break
      sleep 10
    done
  done
  echo "gave up waiting before $1"; exit 1
}
snaps() { curl -s -m 10 http://127.0.0.1:3000/snapshots > "$O/snapshots/$1.json" || true; }

pause100() {  # same extension as nvme1-B-20261027/tools/run-all.sh
  local out=$O/extended-pause-c100 rc=0
  mkdir "$out"
  bash cube-perf-bench/scripts/community-native.sh check pause-c10 >"$out/prerequisites.log" 2>&1
  printf 'case=extended-pause-c100 profile=extended source_ref=%s\n' "$CPB_UPSTREAM_REF" >"$out/invocation.txt"
  printf '%q ' "$CPB_PYTHON" -E -s -B "$CPB_UPSTREAM_DIR/examples/snapshot-rollback-clone/bench_pause_resume_concurrency.py" -c 100 -n 5 >>"$out/invocation.txt"
  printf '\nSeparate extension; same prerequisites as native pause-c10; not a CPB built-in case.\n' >>"$out/invocation.txt"
  "$CPB_PYTHON" -E -s -B "$CPB_UPSTREAM_DIR/examples/snapshot-rollback-clone/bench_pause_resume_concurrency.py" -c 100 -n 5 >"$out/stdout.log" 2>"$out/stderr.log" || rc=$?
  echo "$rc" >"$out/exit-code"
  return "$rc"
}

one() {  # one <case>
  local name=$1 dir=$1 s e o1 o2 rc=0 b1 b2 a1 a2 l1
  sleep 15
  gate "$dir"
  snaps "$dir-before"
  l1=$(cut -d' ' -f1 /proc/loadavg); read -r b1 a1 < <(busy)
  s=$(date -u +%FT%T.%NZ); o1=$(stat -c %s "$API_LOG")
  if [[ $name == extended-pause-c100 ]]; then
    pause100 >"$O/$dir-entry.log" 2>&1 || rc=$?
  else
    CPB_RUN_DIR=$O/$dir bash cube-perf-bench/scripts/community-native.sh run "$name" --authorize-run --exclusive-template >"$O/$dir-entry.log" 2>&1 || rc=$?
  fi
  e=$(date -u +%FT%T.%NZ); o2=$(stat -c %s "$API_LOG"); read -r b2 a2 < <(busy)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$dir" "$s" "$e" "$API_LOG" "$o1" "$o2" "$rc" >> "$O/windows.tsv"
  awk -v n="$dir" -v s="$s" -v e="$e" -v l="$l1" -v b1="$b1" -v b2="$b2" -v a1="$a1" -v a2="$a2" \
      -v h="$(awk '/HugePages_Free/{print $2}' /proc/meminfo)" \
      'BEGIN{printf "%s\t%s\t%s\t%s\t%.2f\t%s\n", n, s, e, l, (b2-b1)*100/(a2-a1), h}' >> "$O/host-load.tsv"
  printf '%s %s rc=%s\n' "$e" "$dir" "$rc"
  if [[ -d $O/$dir ]]; then
    tail -n 4 "$O/$dir/stdout.log" || true
    python3 tools/cleanup-owned.py "$O/$dir" || echo "cleanup failed $dir"
  fi
  snaps "$dir-after"
  cmp -s "$O/snapshots/$dir-before.json" "$O/snapshots/$dir-after.json" || echo "snapshot list changed in $dir"
  [[ $rc == 0 ]] || echo "failed $dir rc=$rc (continuing)"
}

python3 tools/host-conditions.py "$O/conditions-before.json"
for c in create-c50 clone-c10n100 clone-c50n100 extended-startup-c200n200; do one "$c"; done
awk -F'\t' 'NR>1 && $7!=0 {print "nonzero rc:", $1, $7}' "$O/windows.tsv"
grep -a -n -o "Cube-Hypervisor version [^,]*" /data/log/CubeVmm/vmm.log | awk -F: '{print $2}' | uniq -c > "$O/vmm-version-sequence.txt"
sleep 15
gate after
python3 tools/host-conditions.py "$O/conditions-after.json"
echo "ALL DONE $(date -u +%FT%TZ)"
