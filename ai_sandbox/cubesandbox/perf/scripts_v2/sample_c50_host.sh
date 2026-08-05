#!/usr/bin/env bash
set -euo pipefail

output=${1:?usage: sample_c50_host.sh OUTPUT [DURATION_SECONDS] [INTERVAL_SECONDS]}
duration=${2:-12}
interval=${3:-0.1}

mkdir -p "$(dirname "$output")"
printf '%s\n' \
    'uptime_s,user,nice,system,idle,iowait,irq,softirq,steal,ctxt,processes,procs_running,procs_blocked,intr,softirq_total,load1,runnable,threads,mem_available_kib,dirty_kib,writeback_kib,shim_count,vmm_processes' \
    >"$output"

deadline=$(awk -v now="$(cut -d' ' -f1 /proc/uptime)" -v duration="$duration" \
    'BEGIN { printf "%.2f", now + duration }')

while :; do
    uptime_s=$(cut -d' ' -f1 /proc/uptime)
    awk -v uptime_s="$uptime_s" '
        FILENAME == "/proc/stat" && $1 == "cpu" {
            user=$2; nice=$3; sys=$4; idle=$5; iowait=$6; irq=$7;
            softirq=$8; steal=$9
        }
        FILENAME == "/proc/stat" && $1 == "ctxt" { ctxt=$2 }
        FILENAME == "/proc/stat" && $1 == "processes" { processes=$2 }
        FILENAME == "/proc/stat" && $1 == "procs_running" { running=$2 }
        FILENAME == "/proc/stat" && $1 == "procs_blocked" { blocked=$2 }
        FILENAME == "/proc/stat" && $1 == "intr" { intr=$2 }
        FILENAME == "/proc/stat" && $1 == "softirq" { softirq_total=$2 }
        FILENAME == "/proc/loadavg" {
            load1=$1; split($4, tasks, "/"); runnable=tasks[1]; threads=tasks[2]
        }
        FILENAME == "/proc/meminfo" && $1 == "MemAvailable:" { mem_available=$2 }
        FILENAME == "/proc/meminfo" && $1 == "Dirty:" { dirty=$2 }
        FILENAME == "/proc/meminfo" && $1 == "Writeback:" { writeback=$2 }
        END {
            printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s", \
                uptime_s,user,nice,sys,idle,iowait,irq,softirq,steal,ctxt,processes, \
                running,blocked,intr,softirq_total,load1,runnable,threads,mem_available, \
                dirty,writeback
        }
    ' /proc/stat /proc/loadavg /proc/meminfo >>"$output"

    shim_count=$(pgrep -fc '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true)
    vmm_processes=$(pgrep -fc '/cloud-hypervisor|/cube-vmm|/vmm ' || true)
    printf ',%s,%s\n' "$shim_count" "$vmm_processes" >>"$output"

    awk -v now="$uptime_s" -v deadline="$deadline" 'BEGIN { exit !(now >= deadline) }' && break
    sleep "$interval"
done
