#!/usr/bin/env bash
# deploy-and-test-icc-fix.sh
# Deploy the icc_regs.rs u64-fix cube-runtime on .90 and run 20 serial
# creates against the community-image template, counting
# `reset guest time failed` / PortBindingFailed failures.
set -uo pipefail

new_binary=$1     # path to freshly built cube-hypervisor on .90
evidence_dir=$2
template_id=${3:-tpl-42e1ad04f7354b1295e05b78}
rounds=${4:-20}

live=/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime
api_url=http://127.0.0.1:3000
api_key=e2b_000000
shim_bin=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs

mkdir -p "$evidence_dir"
exec > >(tee -a "$evidence_dir/deploy-test.log") 2>&1
log() { printf '%s %s\n' "$(date -Is)" "$*"; }

[[ -f $new_binary ]] || { log "ABORT missing $new_binary"; exit 1; }

cp -a "$live" "$evidence_dir/cube-runtime.pre-icc-fix"
sha256sum "$live" "$new_binary" | tee "$evidence_dir/binaries.sha256"

mapfile -t pids < <(pgrep -f "^${shim_bin} " || true)
if ((${#pids[@]})); then kill -KILL "${pids[@]}" 2>/dev/null; sleep 1; fi

systemctl stop cube-sandbox-cubelet.service
install -m 0755 "$new_binary" "$live"
sync "$live"
systemctl start cube-sandbox-cubelet.service
for i in $(seq 1 60); do
    curl -fsS --max-time 3 "$api_url/cubeapi/v1/health" >/dev/null 2>&1 && break
    sleep 2
done
curl -fsS --max-time 3 "$api_url/cubeapi/v1/health" >/dev/null || { log "ABORT cubelet unhealthy"; exit 1; }
log "DEPLOYED icc-fix cube-runtime"

pass=0; fail=0
for i in $(seq 1 "$rounds"); do
    resp=$(curl -sS --max-time 45 -X POST -H "Authorization: Bearer $api_key" \
        -H 'Content-Type: application/json' \
        -d "{\"templateID\":\"$template_id\"}" "$api_url/sandboxes" 2>&1)
    sid=$(printf '%s' "$resp" | jq -r '.sandboxID // .sandbox_id // .id // empty' 2>/dev/null)
    if [[ -n $sid ]]; then
        pass=$((pass + 1))
        log "attempt-$i PASS $sid"
        curl -fsS --max-time 30 -o /dev/null -X DELETE \
            -H "Authorization: Bearer $api_key" "$api_url/sandboxes/$sid" || true
    else
        fail=$((fail + 1))
        sig=$(printf '%s' "$resp" | grep -oE "reset guest time failed|PortBindingFailed|reset reseed random dev failed" | head -1)
        log "attempt-$i FAIL sig=${sig:-other}"
        printf '%s\n' "$resp" > "$evidence_dir/fail-$i.json"
    fi
    mapfile -t pids < <(pgrep -f "^${shim_bin} " || true)
    if ((${#pids[@]})); then
        kill -TERM "${pids[@]}" 2>/dev/null; sleep 2
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && kill -KILL "$p"; done
    fi
    sleep 1
done
log "RESULT pass=$pass fail=$fail (rounds=$rounds)"
