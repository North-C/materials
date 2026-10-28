#!/usr/bin/env bash
# Wait (max 12 h; second watcher from 10-28 06:20 CST) until no qemu-kvm/ffmpeg/x265 process and load1<=4 on 3 consecutive 60 s checks, then start run-resume.sh.
# Added 10-28 00:13 CST after a foreign 96-vCPU libvirt VM (foreign-vm) started at 00:10:55 and the gate refused.
set -u
R=/path/to/workdir/nvme1-A-20261027/results
ok=0
for i in $(seq 1 720); do
  busy=$(pgrep -x "qemu-kvm|ffmpeg|x265" | wc -l); l=$(cut -d" " -f1 /proc/loadavg)
  if [[ $busy == 0 ]] && awk -v l="$l" "BEGIN{exit !(l<=4.0)}"; then ok=$((ok+1)); else ok=0; fi
  printf "%s busy=%s load1=%s ok=%s\n" "$(date -u +%FT%TZ)" "$busy" "$l" "$ok"
  if [[ $ok -ge 3 ]]; then echo "starting resume"; exec /bin/bash "$R/../tools/run-resume.sh" > "$R/run-resume.log" 2>&1; fi
  sleep 60
done
echo "gave up after 12 h"
