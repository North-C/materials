#!/usr/bin/env bash
# pass-control-physical-timer.sh
# 1. Snapshot /proc/interrupts (KVM vtimer PPI) before.
# 2. Create sandboxes from the community-image template until one PASSES
#    (fail storms are expected; count them and snapshot interrupts again
#    right after a storm, while the orphan is still alive).
# 3. On a healthy sandbox, attach trace_arm64_irq27_entry_pstate_pass.bt
#    for the 5s control capture, then delete the sandbox.
set -uo pipefail

evidence_dir=$1
template_id=$2
api_url=http://127.0.0.1:3000
api_key=e2b_000000
shim_bin=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
bt_dir=/home/lyq/arm64-entry-pstate-repro-20260730

mkdir -p "$evidence_dir"
exec > >(tee -a "$evidence_dir/run.log") 2>&1
log() { printf '%s %s\n' "$(date -Is)" "$*"; }

irq11_line() { grep -E "^\s*11:" /proc/interrupts; }

cleanup_orphans() {
    curl -fsS --max-time 10 -H "Authorization: Bearer $api_key" "$api_url/sandboxes" |
        jq -r '.[] | .sandboxID // .sandbox_id // .id' |
        xargs -r -P 10 -I{} curl -fsS --max-time 30 -o /dev/null -X DELETE \
            -H "Authorization: Bearer $api_key" "$api_url/sandboxes/{}" || true
    sleep 2
    mapfile -t pids < <(pgrep -f "^${shim_bin} " || true)
    if ((${#pids[@]})); then
        kill -TERM "${pids[@]}" 2>/dev/null || true
        sleep 3
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && kill -KILL "$p"; done
    fi
}

irq11_line > "$evidence_dir/interrupts-before.txt"
log "BEGIN template=$template_id"

pass_id=
for attempt in $(seq 1 12); do
    log "ATTEMPT $attempt create..."
    resp=$(curl -sS --max-time 40 -X POST -H "Authorization: Bearer $api_key" \
        -H 'Content-Type: application/json' \
        -d "{\"templateID\":\"$template_id\"}" "$api_url/sandboxes" 2>&1)
    rc=$?
    sid=$(printf '%s' "$resp" | jq -r '.sandboxID // .sandbox_id // .id // empty' 2>/dev/null)
    if [[ $rc == 0 && -n $sid ]]; then
        log "ATTEMPT $attempt PASS sandbox=$sid"
        pass_id=$sid
        break
    fi
    log "ATTEMPT $attempt FAIL rc=$rc resp=$(printf '%s' "$resp" | head -c 200)"
    irq11_line > "$evidence_dir/interrupts-after-fail-$attempt.txt"
    ps -o pid,psr,etime,comm -p "$(pgrep -f "^${shim_bin} " | head -1)" \
        > "$evidence_dir/storm-shim-$attempt.txt" 2>/dev/null || true
    cleanup_orphans
done

irq11_line > "$evidence_dir/interrupts-after-storms.txt"

if [[ -z $pass_id ]]; then
    log "NO_PASS after all attempts"
    exit 1
fi

log "CONTROL attach pass probe for healthy sandbox $pass_id"
# find the VMM (shim) pid for this sandbox and its vcpu1 pcpu
ps -eo pid,psr,cmd | grep "$shim_bin" | grep -v grep > "$evidence_dir/pass-shim-ps.txt" || true
timeout 60 bpftrace "$bt_dir/trace_arm64_irq27_entry_pstate_pass.bt" \
    > "$evidence_dir/pass-probe.log" 2> "$evidence_dir/pass-probe.stderr"
log "CONTROL probe rc=$?"

curl -fsS --max-time 30 -o /dev/null -X DELETE -H "Authorization: Bearer $api_key" \
    "$api_url/sandboxes/$pass_id" || true
sleep 2
cleanup_orphans
irq11_line > "$evidence_dir/interrupts-final.txt"
log "DONE"
