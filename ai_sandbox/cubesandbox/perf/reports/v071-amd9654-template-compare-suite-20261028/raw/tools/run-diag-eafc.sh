#!/usr/bin/env bash
# DIAGNOSTIC (19:55 CST): same bash c100 on peer-isnotfc-bench-1028 (tpl-eafc8a29, built 19:13) to test whether the ~750 ms guest stall is specific to peer-final-check. Not a performance sample.
# 10-28 evening: run on user-b's template peer-final-check (tpl-8a157507...) with the components as deployed
# by user-b at 19:10 CST (cubelet/cubemaster 2babb6f7 rebuilt 10-28 10:12Z; running shim 2babb6f7 built 10-22).
# Order as requested: c100n100 (1 external warmup + 5 formal), pause c1/c5/c10, startup c50n500, snapshot c10.
# Runner: local cube-perf-bench copy whose template check accepts 2000Mi (user-b templates); upstream copy requires 2048Mi.
# Same per-case gate and cleanup as the 10-27/28 runs; the foreign VM was shut down at 19:23 CST.
set -euo pipefail
B=/path/to/workdir
R=$B/nvme1-peertpl-20261028
O=$R/diag-eafc
cd "$B"
source "$R/tools/test-env-eafc.sh"
API_LOG=$(ls -t /data/log/CubeAPI/cube-api-*.log | head -1)
mkdir -p "$O/gates"
printf 'case\tstart_utc\tend_utc\tapi_log\tapi_off_start\tapi_off_end\trc\n' > "$O/windows.tsv"
printf 'case\tstart_utc\tend_utc\tload1_before\thost_busy_pct\thugepages_free\n' > "$O/host-load.tsv"

busy() { awk '/^cpu /{print $2+$3+$4+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }

one() {  # one <case> <run-dir-name>
  local name=$1 dir=$2 s e o1 o2 rc=0 b1 b2 a1 a2 l1
  sleep 15
  bash "$R/tools/wait-clean.sh" "$O/gates/$dir-before"
  l1=$(cut -d' ' -f1 /proc/loadavg); read -r b1 a1 < <(busy)
  s=$(date -u +%FT%T.%NZ); o1=$(stat -c %s "$API_LOG")
  CPB_RUN_DIR=$O/$dir bash $R/cube-perf-bench-2000mi/scripts/community-native.sh run "$name" --authorize-run --exclusive-template >"$O/$dir-entry.log" 2>&1 || rc=$?
  e=$(date -u +%FT%T.%NZ); o2=$(stat -c %s "$API_LOG"); read -r b2 a2 < <(busy)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$dir" "$s" "$e" "$API_LOG" "$o1" "$o2" "$rc" >> "$O/windows.tsv"
  awk -v n="$dir" -v s="$s" -v e="$e" -v l="$l1" -v b1="$b1" -v b2="$b2" -v a1="$a1" -v a2="$a2" \
      -v h="$(awk '/HugePages_Free/{print $2}' /proc/meminfo)" \
      'BEGIN{printf "%s\t%s\t%s\t%s\t%.2f\t%s\n", n, s, e, l, (b2-b1)*100/(a2-a1), h}' >> "$O/host-load.tsv"
  printf '%s %s rc=%s\n' "$e" "$dir" "$rc"
  if [[ -d $O/$dir ]]; then tail -n 4 "$O/$dir/stdout.log" || true; python3 tools/cleanup-owned.py "$O/$dir"; fi
  [[ $rc == 0 ]] || { echo "failed $dir rc=$rc"; exit "$rc"; }
}

python3 tools/host-conditions.py "$O/conditions-before.json"
for r in warmup 1 2; do
  one extended-startup-c100n100 "c100-$r"
  jq -c '{summary,create}' "$O/c100-$r/cube-bench.json"
done
# 19:35 CST user: run c100n100 only, pause later cases for a profiler analysis.
# for c in pause-c1 pause-c5 pause-c10 startup-c50n500 snapshot-c10; do one "$c" "$c"; done
grep -a -n -o "Cube-Hypervisor version [^,]*" /data/log/CubeVmm/vmm.log | awk -F: '{print $2}' | uniq -c > "$O/vmm-version-sequence.txt"
sleep 15
bash "$R/tools/wait-clean.sh" "$O/gates/after"
python3 tools/host-conditions.py "$O/conditions-after.json"
echo "ALL DONE $(date -u +%FT%TZ)"
