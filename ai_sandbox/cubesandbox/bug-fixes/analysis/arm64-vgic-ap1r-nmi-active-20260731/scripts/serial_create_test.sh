#!/usr/bin/env bash
# serial_create_test.sh TEMPLATE_ID ROUNDS LOGFILE — serial create/delete with orphan cleanup
set -uo pipefail
template_id=$1
rounds=$2
logfile=$3
api_url=http://127.0.0.1:3000
api_key=e2b_000000
shim_bin=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs

pass=0; fail=0
: > "$logfile"
for i in $(seq 1 "$rounds"); do
    resp=$(curl -sS --max-time 45 -X POST -H "Authorization: Bearer $api_key" \
        -H 'Content-Type: application/json' \
        -d "{\"templateID\":\"$template_id\"}" "$api_url/sandboxes" 2>&1)
    sid=$(printf '%s' "$resp" | jq -r '.sandboxID // .sandbox_id // .id // empty' 2>/dev/null)
    if [[ -n $sid ]]; then
        pass=$((pass + 1))
        echo "attempt-$i PASS $sid" >> "$logfile"
        curl -fsS --max-time 30 -o /dev/null -X DELETE \
            -H "Authorization: Bearer $api_key" "$api_url/sandboxes/$sid" || true
    else
        fail=$((fail + 1))
        sig=$(printf '%s' "$resp" | grep -oE "reset guest time failed|reset reseed random dev failed|no more resource|PortBindingFailed" | head -1)
        echo "attempt-$i FAIL sig=${sig:-other} $(printf '%s' "$resp" | head -c 120)" >> "$logfile"
    fi
    mapfile -t pids < <(pgrep -f "^${shim_bin} " || true)
    if ((${#pids[@]})); then
        kill -TERM "${pids[@]}" 2>/dev/null; sleep 2
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && kill -KILL "$p"; done
    fi
    sleep 1
done
echo "RESULT pass=$pass fail=$fail rounds=$rounds template=$template_id" >> "$logfile"
