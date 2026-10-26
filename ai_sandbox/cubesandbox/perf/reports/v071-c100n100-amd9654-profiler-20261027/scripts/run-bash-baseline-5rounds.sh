#!/bin/bash
OUT=$1
export E2B_API_URL=http://127.0.0.1:3000 E2B_API_KEY="<redacted>" CUBE_TEMPLATE_ID=tpl-947123cfa84540d68f7c5933
BENCH=/home/lyq/cube-perf-suite/examples/cube-bench/bin/cube-bench
log(){ echo "$(date +%T.%3N) $*" >> $OUT/progress.log; }
count(){ curl -s $E2B_API_URL/health | jq -r .sandboxes; }
for r in 1 2 3 4 5; do
  export CUBE_PERF_RUN_ID=c100n100-r$r-$(date +%s)
  log "round $r start run_id=$CUBE_PERF_RUN_ID sandboxes=$(count) memavail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
  $BENCH -c 100 -n 100 -w 3 -m create-only --no-tui -o $OUT/round$r.json > $OUT/round$r.txt 2>&1
  log "round $r bench rc=$? sandboxes=$(count) memavail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
  curl -s $E2B_API_URL/sandboxes | jq -r --arg id "$CUBE_PERF_RUN_ID" '.[] | select((.metadata // {}).perf_suite_run == $id) | .sandboxID' > $OUT/round$r.ids
  log "round $r deleting $(wc -l < $OUT/round$r.ids) tagged"
  xargs -P 50 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $E2B_API_URL/sandboxes/{} < $OUT/round$r.ids | sort | uniq -c >> $OUT/progress.log
  for i in $(seq 1 90); do [ "$(count)" = 0 ] && break; sleep 2; done
  log "round $r cleaned sandboxes=$(count)"
  [ "$(count)" = 0 ] || { log "ABORT: sandboxes not drained"; exit 1; }
  sleep 30
done
log DONE
