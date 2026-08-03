#!/usr/bin/env bash
# multi_template_concurrent_validation.sh
# On aprmask kernel + icc-fixed VMM: create 2 extra templates from the
# community-image template's create_request, then run cube-bench
# create-only concurrency matrix across 3 templates. Attach-ready for
# the ap1r pollution probe (started separately).
set -uo pipefail

evidence_dir=$1
base_template=tpl-42e1ad04f7354b1295e05b78
api_url=http://127.0.0.1:3000
master_url=http://127.0.0.1:8089
api_key=e2b_000000
bench=/home/lyq/cubesandbox-core-perf-v3-noearly-20260728-194721/tools/cube-bench
fixed_vmm=/tmp/cube-runtime.iccfixed
live_vmm=/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime
shim_bin=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs

mkdir -p "$evidence_dir"
exec > >(tee -a "$evidence_dir/run.log") 2>&1
log() { printf '%s %s\n' "$(date -Is)" "$*"; }

cleanup_orphans() {
    curl -fsS --max-time 10 -H "Authorization: Bearer $api_key" "$api_url/sandboxes" |
        jq -r '.[] | .sandboxID // .sandbox_id // .id' |
        xargs -r -P 20 -I{} curl -fsS --max-time 45 -o /dev/null -X DELETE \
            -H "Authorization: Bearer $api_key" "$api_url/sandboxes/{}" || true
    sleep 3
    mapfile -t pids < <(pgrep -f "^${shim_bin} " || true)
    if ((${#pids[@]})); then
        kill -TERM "${pids[@]}" 2>/dev/null || true
        sleep 3
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && kill -KILL "$p"; done
    fi
}

# 1. Deploy fixed VMM
[[ -f $fixed_vmm ]] || { log "ABORT missing $fixed_vmm"; exit 1; }
install -m 0755 "$fixed_vmm" "$live_vmm"
systemctl restart cube-sandbox-cubelet.service
for i in $(seq 1 45); do
    curl -fsS --max-time 3 "$api_url/cubeapi/v1/health" >/dev/null 2>&1 && break
    sleep 2
done
curl -fsS --max-time 3 "$api_url/cubeapi/v1/health" >/dev/null || { log "ABORT cubelet unhealthy"; exit 1; }
log "FIXED-VMM deployed $(sha256sum "$live_vmm" | cut -c1-16)"

# 2. Create two extra templates from the base create_request
curl -fsS --max-time 30 "$master_url/cube/template?template_id=$base_template&include_request=true" \
    > "$evidence_dir/base-template-info.json"
jq '.create_request' "$evidence_dir/base-template-info.json" > "$evidence_dir/base-request.json"

make_template() {
    local tag=$1
    local tid=tpl-$(tr -d '-' </proc/sys/kernel/random/uuid | cut -c1-24)
    local rid=$(cat /proc/sys/kernel/random/uuid)
    jq --arg tid "$tid" --arg rid "$rid" \
        '.requestID = $rid | .annotations["cube.master.appsnapshot.template.id"] = $tid' \
        "$evidence_dir/base-request.json" > "$evidence_dir/template-request-$tag.json"
    local code
    code=$(curl -sS --max-time 900 -o "$evidence_dir/template-create-$tag.json" -w '%{http_code}' \
        -X POST -H 'Content-Type: application/json' \
        --data-binary "@$evidence_dir/template-request-$tag.json" \
        "$master_url/cube/template")
    local status
    status=$(jq -r '.status // "?"' "$evidence_dir/template-create-$tag.json" 2>/dev/null)
    log "TEMPLATE $tag $tid http=$code status=$status"
    if [[ $code == 200 && $status == READY ]]; then
        printf '%s' "$tid"
        return 0
    fi
    return 1
}

tpl_b=$(make_template B) || { log "ABORT template B create failed"; exit 1; }
tpl_c=$(make_template C) || { log "ABORT template C create failed"; exit 1; }
echo "$tpl_b" > "$evidence_dir/tpl-b.id"
echo "$tpl_c" > "$evidence_dir/tpl-c.id"

run_bench() {
    local tag=$1 tpl=$2 c=$3 n=$4
    cleanup_orphans
    log "BENCH $tag tpl=$tpl c=$c n=$n start"
    timeout --signal=TERM --kill-after=30s 30m \
        "$bench" -api-url "$api_url" -api-key "$api_key" \
        -template "$tpl" -c "$c" -n "$n" -w 3 \
        -m create-only -no-tui -o "$evidence_dir/bench-$tag.json" \
        > "$evidence_dir/bench-$tag.out" 2>&1
    local rc=$?
    if [[ -s $evidence_dir/bench-$tag.json ]]; then
        jq -c --arg tag "$tag" --argjson rc "$rc" \
            '{tag:$tag, bench_rc:$rc, successful:(.summary.successful // 0), errors:(.summary.errors // 0)}' \
            "$evidence_dir/bench-$tag.json" | tee -a "$evidence_dir/bench-summary.jsonl"
    else
        log "BENCH $tag rc=$rc no-report"
    fi
    cleanup_orphans
    log "BENCH $tag done rc=$rc"
}

: > "$evidence_dir/bench-summary.jsonl"
run_bench A-c10n200 "$base_template" 10 200
run_bench A-c20n300 "$base_template" 20 300
run_bench A-c50n500 "$base_template" 50 500
run_bench B-c20n300 "$tpl_b" 20 300
run_bench C-c20n300 "$tpl_c" 20 300

# failure signature scan
grep -c "reset guest time failed" /data/log/CubeShim/cube-shim-req.log 2>/dev/null \
    > "$evidence_dir/shim-reset-guest-time-count.txt" || true
grep -c "reset reseed random dev failed" /data/log/CubeShim/cube-shim-req.log 2>/dev/null \
    > "$evidence_dir/shim-reset-reseed-count.txt" || true
log "ALL-DONE"
