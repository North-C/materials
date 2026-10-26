#!/bin/bash
OUT=$1; T=/home/lyq/cube-startup-profiler
export E2B_API_URL=http://127.0.0.1:3000 E2B_API_KEY="<redacted>"
log(){ echo "$(date +%T.%3N) $*" >> $OUT/progress.log; }
cnt(){ curl -s $E2B_API_URL/sandboxes | jq length; }
for r in 1 2 3 4 5; do
  [ "$(cnt)" = 0 ] || { log "ABORT: sandboxes present before round $r"; exit 1; }
  export CUBE_PERF_RUN_ID=prof-r$r-$(date +%s)
  mkdir -p $OUT/r$r
  log "round $r start run_id=$CUBE_PERF_RUN_ID"
  (cd $T && python3 capture_100.py --config $T/capture100.local.json --output-root $OUT/r$r > $OUT/r$r/console.log 2>&1)
  log "round $r capture rc=$? live=$(cnt)"
  curl -s $E2B_API_URL/sandboxes | jq -r --arg id "$CUBE_PERF_RUN_ID" '.[] | select((.metadata // {}).perf_suite_run == $id) | .sandboxID' > $OUT/r$r/owned.ids
  log "round $r deleting $(wc -l < $OUT/r$r/owned.ids) tagged"
  xargs -P 50 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $E2B_API_URL/sandboxes/{} < $OUT/r$r/owned.ids | sort | uniq -c >> $OUT/progress.log
  for i in $(seq 1 90); do [ "$(cnt)" = 0 ] && break; sleep 2; done
  log "round $r cleaned live=$(cnt)"
  [ "$(cnt)" = 0 ] || { log "ABORT: not drained (untagged sandboxes left untouched)"; exit 1; }
  sleep 30
done
chown -R lyq:lyq $OUT
log DONE
