#!/usr/bin/env bash
# After the bash c100n100 five rounds (run-peertpl.sh) print ALL DONE, run cube-startup-profiler 45df527
# for 5 rounds on peer-final-check (tpl-8a157507...). capture_100.py launches cube-bench from Python
# (c100 n100 w3 create-only); the bash rounds are the baseline for that launch-path difference.
# Each round: same gate as the bash runs, then capture, then delete only this template's instances
# started inside the round window. Aborts if the bash run failed or the host is not quiet.
set -uo pipefail
B=/path/to/workdir
R=$B/nvme1-peertpl-20261028
P=/path/to/home/cube-startup-profiler-45df527
O=$R/profiler
TPL=tpl-8a157507644a426f9e7a6326
API=http://127.0.0.1:3000
mkdir -p "$O/gates"
log() { echo "$(date -u +%FT%T.%3NZ) $*" | tee -a "$O/progress.log"; }
cnt() { curl -s -m 10 $API/sandboxes | jq length; }

for i in $(seq 1 2160); do
  grep -q '^ALL DONE' "$R/results/run.log" 2>/dev/null && break
  grep -qE '^failed |gave up' "$R/results/run.log" "$R/results/wait-then-run.log" 2>/dev/null && { log "ABORT: bash c100 run failed or gave up"; exit 1; }
  sleep 10
done
grep -q '^ALL DONE' "$R/results/run.log" || { log "ABORT: bash c100 not done after 6 h"; exit 1; }
log "bash c100 done; starting profiler rounds"
cd "$B"
for r in 1 2 3 4 5; do
  sleep 30
  bash "$R/tools/wait-clean.sh" "$O/gates/r$r-before" || { log "ABORT: gate failed before round $r"; exit 1; }
  mkdir -p "$O/r$r"
  s=$(date -u +%FT%T.%NZ); l1=$(cut -d' ' -f1 /proc/loadavg)
  log "round $r start load1=$l1"
  (cd "$P" && python3 capture_100.py --config "$P/capture100.local.json" --output-root "$O/r$r" > "$O/r$r/console.log" 2>&1)
  rc=$?; e=$(date -u +%FT%T.%NZ)
  printf '%s\t%s\t%s\t%s\n' "r$r" "$s" "$e" "$rc" >> "$O/windows.tsv"
  log "round $r capture rc=$rc live=$(cnt)"
  curl -s -m 20 $API/sandboxes > "$O/r$r/inventory-before-cleanup.json"
  jq -r --arg t "$TPL" --arg s "$s" '.[] | select(.templateID == $t and .startedAt >= $s) | .sandboxID' "$O/r$r/inventory-before-cleanup.json" > "$O/r$r/owned.ids"
  log "round $r deleting $(wc -l < "$O/r$r/owned.ids") instances of $TPL started after $s"
  xargs -P 20 -I{} curl -s -o /dev/null -m 120 -w '%{http_code}\n' -X DELETE $API/sandboxes/{} < "$O/r$r/owned.ids" | sort | uniq -c | tee -a "$O/progress.log"
  for i in $(seq 1 90); do [ "$(cnt)" = 0 ] && break; sleep 2; done
  log "round $r cleaned live=$(cnt)"
  [ "$(cnt)" = 0 ] || { log "ABORT: inventory not empty after cleanup (other instances left untouched)"; exit 1; }
  [ $rc = 0 ] || { log "ABORT: capture rc=$rc"; exit 1; }
done
log DONE
