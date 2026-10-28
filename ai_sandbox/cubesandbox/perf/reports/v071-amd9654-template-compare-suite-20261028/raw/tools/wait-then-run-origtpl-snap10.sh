#!/usr/bin/env bash
# Wait until other users' Cube benchmarks are done and the host is quiet, then run run-origtpl-snap10.sh.
# Quiet = no create_bench/pause_resume_bench/cube-bench process, CubeAPI inventory empty, load1 <= 4,
# for 2 consecutive 10 s checks (user 19:44: start as soon as no other test runs). Gives up after 3 h.
set -uo pipefail
R=/path/to/workdir/nvme1-peertpl-20261028
ok=0
for i in $(seq 1 1080); do
  b=$(pgrep -fc '[c]reate_bench|[p]ause_resume_bench|[c]ube-bench ' || true)
  n=$(curl -s -m 10 http://127.0.0.1:3000/sandboxes | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo err)
  l=$(cut -d' ' -f1 /proc/loadavg)
  if [[ $b == 0 && $n == 0 ]] && awk -v l="$l" 'BEGIN{exit !(l<=4)}'; then ok=$((ok+1)); else ok=0; fi
  echo "$(date -u +%FT%TZ) bench=$b inventory=$n load1=$l ok=$ok"
  if (( ok >= 2 )); then
    echo "quiet; launching run-origtpl-snap10.sh"
    cd /path/to/workdir && exec /bin/bash "$R/tools/run-origtpl-snap10.sh" > "$R/results-origtpl-snap10-2055/run.log" 2>&1
  fi
  sleep 10
done
echo "gave up after 3 h"
