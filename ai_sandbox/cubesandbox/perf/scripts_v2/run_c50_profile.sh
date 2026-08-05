#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base_dir=${BASE_DIR:-/home/lyq/cubesandbox-c50-optimization-20260727-220353}
out_dir=${OUT_DIR:-$base_dir/baseline-profile-2}
runner=${RUNNER:-$script_dir/run_cubesandbox_openeuler_template_perf.sh}
host_sampler=${HOST_SAMPLER:-$script_dir/sample_c50_host.sh}
case_name=${CASE_NAME:-profile-c50-n500}
template_id=${TEMPLATE_ID:-tpl-297f00a33adb43de957bbf90}
api_log=${API_LOG:-$(find /data/log/CubeAPI -maxdepth 1 -type f -name 'cube-api-*.log' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)}

if [[ -z "$api_log" ]]; then
  printf 'no CubeAPI log found under /data/log/CubeAPI\n' >&2
  exit 1
fi

mkdir -p "$out_dir/evidence"
rm -f "$out_dir/run.log"

for entry in \
  cubelet_req:/data/log/Cubelet/Cubelet-req.log \
  cubelet_stat:/data/log/Cubelet/Cubelet-stat.log \
  shim_req:/data/log/CubeShim/cube-shim-req.log \
  shim_stat:/data/log/CubeShim/cube-shim-stat.log \
  vmm:/data/log/CubeVmm/vmm.log \
  master:/data/log/CubeMaster/cubemaster-req.log \
  api:"$api_log"; do
  name=${entry%%:*}
  path=${entry#*:}
  stat -c "$name %n %s %i" "$path"
done >"$out_dir/evidence/log-offsets-before.txt"

curl -fsS http://127.0.0.1:9998/v1/metrics >"$out_dir/evidence/metrics-before.prom"

(
  deadline=$((SECONDS + 60))
  while ! rg -q "STARTUP_BEGIN name=${case_name} " "$out_dir/run.log" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      printf 'profile trigger timed out for case %s\n' "$case_name" \
        >"$out_dir/evidence/profile-trigger-error.txt"
      exit 1
    fi
    sleep 0.05
  done

  date -Is >"$out_dir/evidence/profile-triggered-at.txt"
  "$host_sampler" \
    "$out_dir/evidence/host-samples.csv" 12 0.1 &
  sampler_pid=$!

  bpftrace -o "$out_dir/evidence/bpftrace-profile.txt" -e '
    profile:hz:19 /comm == "cubelet" || comm == "cubemaster" || comm == "network-agent"/ {
      @service_kernel[comm, kstack] = count();
      @service_user[comm, ustack] = count();
    }
    profile:hz:19 /comm == "vcpu0" || comm == "vcpu1" || comm == "cloud-hypervis" || comm == "cube-vmm"/ {
      @vm_kernel[comm, kstack] = count();
    }
    interval:s:8 { exit(); }
  ' >"$out_dir/evidence/bpftrace-launch.log" 2>&1 &
  tracer_pid=$!

  for second in $(seq 0 8); do
    {
      printf 'snapshot_at=%s second=%s\n' "$(date -Is)" "$second"
      ps -eLo pid,tid,ppid,psr,stat,pcpu,pmem,comm,wchan:32,args \
        --sort=-pcpu | head -400
    } >"$out_dir/evidence/process-snapshot-$second.txt"
    sleep 1
  done

  wait "$sampler_pid" || true
  wait "$tracer_pid" || true
) &
watcher_pid=$!

set +e
WORKDIR="$out_dir" \
TEMPLATE_ID="$template_id" \
RUN_STARTUP=1 \
RUN_DENSITY=0 \
RETRY_UNTIL_SUCCESS=0 \
TAP_TARGET=1000 \
CASE_MATRIX="$case_name 50 500" \
  "$runner"
runner_rc=$?
set -e

watcher_rc=0
wait "$watcher_pid" || watcher_rc=$?

curl -fsS http://127.0.0.1:9998/v1/metrics >"$out_dir/evidence/metrics-after.prom"

: >"$out_dir/evidence/log-offsets-after.txt"
while read -r name log_path before_size before_inode; do
  current_size=$(stat -c %s "$log_path")
  current_inode=$(stat -c %i "$log_path")
  printf '%s %s %s %s\n' "$name" "$log_path" "$current_size" "$current_inode" \
    >>"$out_dir/evidence/log-offsets-after.txt"

  delta_path="$out_dir/evidence/$name-delta.log"
  if [[ "$current_inode" == "$before_inode" && "$current_size" -ge "$before_size" ]]; then
    tail -c "+$((before_size + 1))" "$log_path" >"$delta_path"
  else
    cp "$log_path" "$delta_path"
    printf '%s inode_or_size_changed before_size=%s before_inode=%s after_size=%s after_inode=%s\n' \
      "$name" "$before_size" "$before_inode" "$current_size" "$current_inode" \
      >>"$out_dir/evidence/log-rotation-warnings.txt"
  fi
done <"$out_dir/evidence/log-offsets-before.txt"

create_container_events="$out_dir/evidence/create-container-events.jsonl"
jq -c '
  select((.InstanceId? // "") != "") |
  select((.LogContent? | type) == "string") |
  select(.LogContent | test(
    "^(create req start|load spec finish at:|start vm start|agent is ready|start sandbox finish at:|exec a child process|exec process start|start container finish at:|create req finish)|" +
    "\\[cube-strace\\]recv create container|create container by restore|created container!, add_devices:"
  ))
' "$out_dir/evidence/shim_req-delta.log" >"$create_container_events"

{
  printf 'schema_version=2\n'
  printf 'source=shim_req-delta.log\n'
  printf 'event_count=%s\n' "$(wc -l <"$create_container_events")"
  printf 'captured_at=%s\n' "$(date -Is)"
} >"$out_dir/evidence/create-container-sampling.txt"

printf '%s\n' "$runner_rc" >"$out_dir/evidence/runner-exit-code.txt"
printf '%s\n' "$watcher_rc" >"$out_dir/evidence/watcher-exit-code.txt"

if (( runner_rc != 0 )); then
  exit "$runner_rc"
fi
exit "$watcher_rc"
