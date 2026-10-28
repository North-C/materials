#!/usr/bin/env bash
# 10-28: c100n100 A -> B -> A2 with the foreign libvirt VM foreign-vm (pid 421105) present.
# User accepted this condition; results are labeled "VM present" and not pooled with the 10-27 night runs.
# A = community 31d911e (current state), B = BoostKit 2babb6f7 + dirty_log=true, A2 = community again (drift check).
# Each phase: 1 external warmup + 5 formal rounds, same per-round gate/cleanup as the 10-27 runs.
set -euo pipefail
B=/path/to/workdir
R=$B/nvme1-vm-20261028
O=$R/results
VM=421105
cd "$B"
source "$R/tools/test-env.sh"
# CubeAPI keeps writing the 10-27 file past midnight; use the file actually being written.
API_LOG=$(ls -t /data/log/CubeAPI/cube-api-*.log | head -1)
mkdir -p "$O/gates"
printf 'case\tstart_utc\tend_utc\tapi_log\tapi_off_start\tapi_off_end\trc\n' > "$O/windows.tsv"
printf 'case\tstart_utc\tend_utc\telapsed_s\tvm_cpu_jiffies\tvm_avg_cores\thost_busy_pct\thugepages_free\n' > "$O/vm-cpu.tsv"

vmj() { awk '{print $14+$15}' /proc/$VM/stat; }
busy() { awk '/^cpu /{print $2+$3+$4+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }

one() {  # one <case> <run-dir-name> <native command...>
  local name=$1 dir=$2; shift 2
  sleep 15
  bash "$R/tools/wait-clean.sh" "$O/gates/$dir-before"
  local s e o1 o2 rc=0 j1 j2 t1 t2 b1 b2 a1 a2
  [[ -e /proc/$VM ]] || echo "note: foreign VM $VM no longer present before $dir"
  j1=$(vmj 2>/dev/null || echo 0); read -r b1 a1 < <(busy); t1=$(date +%s.%N)
  s=$(date -u +%FT%T.%NZ); o1=$(stat -c %s "$API_LOG")
  "$@" >"$O/$dir-entry.log" 2>&1 || rc=$?
  e=$(date -u +%FT%T.%NZ); o2=$(stat -c %s "$API_LOG")
  j2=$(vmj 2>/dev/null || echo 0); read -r b2 a2 < <(busy); t2=$(date +%s.%N)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$s" "$e" "$API_LOG" "$o1" "$o2" "$rc" >> "$O/windows.tsv"
  awk -v n="$dir" -v s="$s" -v e="$e" -v t1="$t1" -v t2="$t2" -v j1="$j1" -v j2="$j2" -v b1="$b1" -v b2="$b2" -v a1="$a1" -v a2="$a2" \
      -v h="$(awk '/HugePages_Free/{print $2}' /proc/meminfo)" \
      'BEGIN{d=t2-t1; printf "%s\t%s\t%s\t%.3f\t%d\t%.2f\t%.2f\t%s\n", n, s, e, d, j2-j1, (j2-j1)/100/d, (b2-b1)*100/(a2-a1), h}' >> "$O/vm-cpu.tsv"
  printf '%s %s rc=%s\n' "$e" "$dir" "$rc"
  if [[ -d $O/$dir ]]; then tail -n 4 "$O/$dir/stdout.log" || true; python3 tools/cleanup-owned.py "$O/$dir"; fi
  [[ $rc == 0 ]] || { echo "failed $dir rc=$rc"; exit "$rc"; }
}
native() { CPB_RUN_DIR=$O/$2 bash cube-perf-bench/scripts/community-native.sh run "$1" --authorize-run --exclusive-template; }

c100() {  # c100 <phase>
  python3 tools/host-conditions.py "$O/conditions-before-$1.json"
  for r in warmup 1 2 3 4 5; do
    one extended-startup-c100n100 "$1-c100-$r" native extended-startup-c100n100 "$1-c100-$r"
    jq -c '{summary,create}' "$O/$1-c100-$r/cube-bench.json"
  done
}
swap() {  # swap <B|A2>
  sleep 15
  bash "$R/tools/wait-clean.sh" "$O/gates/swap-$1-before"
  bash "$R/tools/swap-components.sh" "$1" > "$O/swap-$1.log" 2>&1 || { echo "swap $1 failed"; tail -5 "$O/swap-$1.log"; exit 1; }
  tail -1 "$O/swap-$1.log"
  grep -a -o "Cube-Hypervisor version [^,]*" /data/log/CubeVmm/vmm.log | tail -1
}

c100 A
swap B
c100 B
swap A2
c100 A2
grep -a -n -o "Cube-Hypervisor version [^,]*" /data/log/CubeVmm/vmm.log | awk -F: '{print $2}' | uniq -c > "$O/vmm-version-sequence.txt"
sleep 15
bash "$R/tools/wait-clean.sh" "$O/gates/after"
python3 tools/host-conditions.py "$O/conditions-after.json"
echo "ALL DONE $(date -u +%FT%TZ)"
