#!/usr/bin/env bash
set -euo pipefail
base=/path/to/workdir
out=${1:?output prefix}
for attempt in $(seq 1 20); do
 if python3 "/path/to/workdir/nvme1-B-20261027/tools/gate.py" "$out-attempt-$attempt.json"; then exit 0; fi
 # Only a residual load average can be retried automatically.
 jq -e '.inventory==[] and .tap_total>=600 and .tap_counts.Ready==.tap_total and .active_tap_owners==[] and .conflicting_processes==[]' "$out-attempt-$attempt.json" >/dev/null || exit 1
 echo "Waiting 30s for load gate; attempt $attempt"
 sleep 30
done
exit 1
