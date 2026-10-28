#!/usr/bin/env bash
R=/path/to/workdir/nvme1-peertpl-20261028
for i in $(seq 1 1080); do
  grep -qE "DONE$|ABORT" $R/profiler/progress.log && break
  sleep 10
done
grep -q "DONE$" $R/profiler/progress.log || { echo "profiler did not finish cleanly; diagnostic not run"; exit 1; }
cd /path/to/workdir && exec /bin/bash $R/tools/run-diag-eafc.sh
