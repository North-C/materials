#!/usr/bin/env bash
# Restore .90 CubeSandbox stack binaries to community v0.5.1 (a164417f)
# provenance, then swap the guest image to the preserved community
# (TencentOS) copy, in preparation for reproducing `reset guest time failed`.
#
# Usage: restore_community_stack_for_reset_time_repro.sh EVIDENCE_DIR
#
# Hash-verified community sources on .90:
#   cubelet    88e5e224  (source-clean rebuild from a164417f, 2026-07-25 baseline)
#   shim       4702fde1  (community release build, _output/bin-clean)
#   cubemaster 0b78e83c  (community stack matrix 20260723)
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 EVIDENCE_DIR" >&2
    exit 2
fi

evidence_dir=$1
api_url=${API_URL:-http://127.0.0.1:3000}
api_key=${API_KEY:-e2b_000000}

live_cubelet=/usr/local/services/cubetoolbox/Cubelet/bin/cubelet
live_shim=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
live_master=/usr/local/services/cubetoolbox/CubeMaster/bin/cubemaster
live_image_dir=/usr/local/services/cubetoolbox/cube-image
community_image_dir=/usr/local/services/cubetoolbox/cube-image.community-v0.5.1-tested-20260727-214700
task_dir=/data/cubelet/root/io.containerd.runtime.v2.task

src_cubelet=/home/lyq/CubeSandbox-v0.5.1-arm64-resume-log-only-v25/Cubelet/build/cubelet
src_shim=/home/lyq/CubeSandbox-community-clean-a164417f/_output/bin-clean/containerd-shim-cube-rs
src_master=/home/lyq/cube-community-stack-matrix-20260723-161000/source/CubeMaster/build/cubemaster

want_cubelet=88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96
want_shim=4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d
want_master=0b78e83c218a7d62c6418def13b50cc2e7c0a0e86115d3ff4006d538951014ae

cubelet_svc=cube-sandbox-cubelet.service
master_svc=cube-sandbox-cubemaster.service
rollback_required=0
ts=$(date +%Y%m%d-%H%M%S)

mkdir -p "$evidence_dir/backup" "$evidence_dir/baseline" "$evidence_dir/logs"
exec > >(tee -a "$evidence_dir/logs/restore-community-stack.log") 2>&1

log() { printf '%s %s\n' "$(date -Is)" "$*"; }

sha() { sha256sum "$1" | awk '{print $1}'; }

check_src() {
    local path=$1 want=$2 name=$3
    [[ -f $path ]] || { log "ABORT missing $name source: $path"; exit 1; }
    local got
    got=$(sha "$path")
    [[ $got == "$want" ]] || { log "ABORT $name source hash mismatch got=$got want=$want"; exit 1; }
}

sandbox_count() {
    curl -fsS --max-time 10 -H "Authorization: Bearer $api_key" "$api_url/sandboxes" | jq 'length'
}

wait_for_health() {
    local attempt
    for attempt in $(seq 1 90); do
        if systemctl is-active --quiet "$cubelet_svc" &&
            systemctl is-active --quiet "$master_svc" &&
            curl -fsS --max-time 3 "$api_url/cubeapi/v1/health" >/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

rollback() {
    local rc=$?
    if (( rollback_required )); then
        log "ROLLBACK rc=$rc"
        systemctl stop "$cubelet_svc" "$master_svc" || true
        for f in cubelet shim master; do
            local var="backup_$f" live=""
            case $f in
                cubelet) live=$live_cubelet ;;
                shim)    live=$live_shim ;;
                master)  live=$live_master ;;
            esac
            [[ -f ${!var:-} ]] && install -m 0755 "${!var}" "$live"
        done
        systemctl start "$master_svc" "$cubelet_svc" || true
        wait_for_health || true
    fi
    exit "$rc"
}
trap rollback EXIT

check_src "$src_cubelet" "$want_cubelet" cubelet
check_src "$src_shim" "$want_shim" shim
check_src "$src_master" "$want_master" cubemaster
[[ -d $community_image_dir ]] || { log "ABORT missing community image dir"; exit 1; }

n=$(sandbox_count)
[[ $n == 0 ]] || { log "ABORT active sandboxes=$n"; exit 1; }

mapfile -t shim_pids < <(pgrep -f "^${live_shim} " || true)
task_count=$(find "$task_dir" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l)
[[ ${#shim_pids[@]} == 0 && $task_count == 0 ]] || {
    log "ABORT dirty runtime shims=${#shim_pids[@]} tasks=$task_count"
    exit 1
}
log "PRECHECK ok sandboxes=0 shims=0 tasks=0"

backup_cubelet="$evidence_dir/backup/cubelet.pre-community-$ts"
backup_shim="$evidence_dir/backup/containerd-shim-cube-rs.pre-community-$ts"
backup_master="$evidence_dir/backup/cubemaster.pre-community-$ts"
cp -a "$live_cubelet" "$backup_cubelet"
cp -a "$live_shim" "$backup_shim"
cp -a "$live_master" "$backup_master"
sha256sum "$live_cubelet" "$live_shim" "$live_master" \
    > "$evidence_dir/baseline/binaries-before.sha256"

rollback_required=1
systemctl stop "$cubelet_svc" "$master_svc"

install -m 0755 "$src_cubelet" "$live_cubelet"
install -m 0755 "$src_shim" "$live_shim"
install -m 0755 "$src_master" "$live_master"
sync "$live_cubelet" "$live_shim" "$live_master"

[[ $(sha "$live_cubelet") == "$want_cubelet" ]]
[[ $(sha "$live_shim") == "$want_shim" ]]
[[ $(sha "$live_master") == "$want_master" ]]
log "INSTALLED community binaries"

# Swap guest image to the preserved community (TencentOS) copy.
mv "$live_image_dir" "${live_image_dir}.openEuler-backup-$ts"
cp -a "$community_image_dir" "$live_image_dir"
sync "$live_image_dir"
log "IMAGE swapped to community copy (backup: ${live_image_dir}.openEuler-backup-$ts)"

systemctl start "$master_svc" "$cubelet_svc"
wait_for_health

sleep 3
[[ $(sandbox_count) == 0 ]]
sha256sum "$live_cubelet" "$live_shim" "$live_master" "$live_image_dir/cube-guest-image-cpu.img" \
    > "$evidence_dir/baseline/binaries-after.sha256"
"$live_cubelet" --version > "$evidence_dir/baseline/cubelet.version.txt" 2>&1 || true
systemctl status "$cubelet_svc" "$master_svc" --no-pager \
    > "$evidence_dir/baseline/services-after.txt" 2>&1 || true
curl -fsS --max-time 10 "$api_url/cubeapi/v1/health" \
    > "$evidence_dir/baseline/health-after.json"
cat "$live_image_dir/version" > "$evidence_dir/baseline/guest-image-version.txt"

rollback_required=0
trap - EXIT
log "SUCCESS community stack active (cubelet/shim/cubemaster + community guest image)"
