#!/usr/bin/env bash
set -uo pipefail

WORKDIR=${WORKDIR:?set WORKDIR to the remote result directory}
TEMPLATE_ID=${TEMPLATE_ID:?set TEMPLATE_ID to the benchmark template ID}
API_URL=${API_URL:-http://127.0.0.1:3000}
API_KEY=${API_KEY:-e2b_000000}
BENCH=${BENCH:-/home/zhou/CubeSandbox/examples/cube-bench/bin/cube-bench}
TAP_TARGET=${TAP_TARGET:-1000}

STARTUP_DIR=${STARTUP_DIR:-$WORKDIR/startup-latency}
DENSITY_DIR=${DENSITY_DIR:-$WORKDIR/density}
EVIDENCE_DIR=${EVIDENCE_DIR:-$WORKDIR/evidence}
RUN_DENSITY=${RUN_DENSITY:-1}
RUN_STARTUP=${RUN_STARTUP:-1}
RETRY_UNTIL_SUCCESS=${RETRY_UNTIL_SUCCESS:-0}
CASE_MATRIX=${CASE_MATRIX:-$'create-c1-n20 1 20\ncreate-c10-n200 10 200\ncreate-c20-n300 20 300\ncreate-c50-n500 50 500'}
SHIM_BIN=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
TASK_DIR=/data/cubelet/root/io.containerd.runtime.v2.task
FAILED=0

mkdir -p "$STARTUP_DIR" "$DENSITY_DIR" "$EVIDENCE_DIR"

log() {
    printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$WORKDIR/run.log"
}

sandbox_json() {
    curl -fsS --max-time 15 \
        -H "Authorization: Bearer $API_KEY" \
        "$API_URL/sandboxes"
}

sandbox_count() {
    sandbox_json | jq 'length'
}

shim_count() {
    pgrep -fc "^${SHIM_BIN} " 2>/dev/null || true
}

task_count() {
    find "$TASK_DIR" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l
}

tap_total() {
    find /sys/class/net -mindepth 1 -maxdepth 1 -type l -name 'z*' -printf . | wc -c
}

tap_in_use() {
    local count=0 state path
    for path in /sys/class/net/z*/operstate; do
        state=
        read -r state <"$path" 2>/dev/null || true
        [[ "$state" == up ]] && count=$((count + 1))
    done
    printf '%s\n' "$count"
}

mem_available_kib() {
    awk '$1 == "MemAvailable:" {print $2}' /proc/meminfo
}

wait_for_services() {
    local attempt
    for attempt in $(seq 1 90); do
        if systemctl is-active --quiet cube-sandbox-cubelet.service &&
            systemctl is-active --quiet cube-sandbox-network-agent.service &&
            curl -fsS --max-time 3 "$API_URL/cubeapi/v1/health" >/dev/null &&
            curl -fsS --max-time 3 http://127.0.0.1:19090/healthz >/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

cleanup_sandboxes() {
    local items count round
    for round in $(seq 1 20); do
        items=$(sandbox_json) || return 1
        count=$(jq 'length' <<<"$items") || return 1
        [[ "$count" == 0 ]] && return 0
        jq -r '.[] | .sandboxID // .sandbox_id // .id' <<<"$items" |
            xargs -r -P 50 -I{} curl -fsS --max-time 60 -o /dev/null \
                -X DELETE -H "Authorization: Bearer $API_KEY" \
                "$API_URL/sandboxes/{}" || true
        sleep 2
    done
    return 1
}

recover_empty_runtime() {
    local label=$1
    local before_sandboxes before_shims before_tasks
    local after_sandboxes after_shims after_tasks
    local live pid attempt
    local -a pids=()

    cleanup_sandboxes || {
        log "RECOVERY label=$label api_cleanup=failed"
        return 1
    }
    sleep 2

    before_sandboxes=$(sandbox_count) || return 1
    before_shims=$(shim_count)
    before_tasks=$(task_count)
    printf 'sandboxes=%s\nshims=%s\ntasks=%s\n' \
        "$before_sandboxes" "$before_shims" "$before_tasks" \
        >"$EVIDENCE_DIR/$label.before.txt"

    [[ "$before_sandboxes" == 0 ]] || return 1
    if [[ "$before_shims" != 0 || "$before_tasks" != 0 ]]; then
        ps -eo pid,ppid,pcpu,pmem,etime,args --sort=-pcpu \
            >"$EVIDENCE_DIR/$label.processes-before-recovery.txt"
        log "RECOVERY label=$label shims=$before_shims tasks=$before_tasks"

        mapfile -t pids < <(pgrep -f "^${SHIM_BIN} " || true)
        printf '%s\n' "${pids[@]}" >"$EVIDENCE_DIR/$label.recovered-shim-pids.txt"
        if [[ "$before_tasks" == 0 ]] && ((${#pids[@]})); then
            log "RECOVERY_LIVE label=$label residual_pids=${#pids[@]}"
            kill -TERM "${pids[@]}" 2>/dev/null || true
            for attempt in $(seq 1 20); do
                live=0
                for pid in "${pids[@]}"; do
                    kill -0 "$pid" 2>/dev/null && live=$((live + 1))
                done
                [[ "$live" == 0 ]] && break
                sleep 1
            done
            for pid in "${pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
            done
        fi
        sleep 2

        if [[ "$(shim_count)" != 0 || "$(task_count)" != 0 ]]; then
            systemctl stop cube-sandbox-cubelet.service || return 1
            sleep 2
            mapfile -t pids < <(pgrep -f "^${SHIM_BIN} " || true)
            log "RECOVERY_STOPPED label=$label residual_pids=${#pids[@]}"
            if ((${#pids[@]})); then
                kill -TERM "${pids[@]}" 2>/dev/null || true
                sleep 5
                for pid in "${pids[@]}"; do
                    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
                done
            fi
            for attempt in $(seq 1 30); do
                [[ "$(shim_count)" == 0 && "$(task_count)" == 0 ]] && break
                sleep 1
            done
            [[ "$(shim_count)" == 0 && "$(task_count)" == 0 ]] || return 1
            systemctl reset-failed cube-sandbox-cubelet.service || true
            systemctl start cube-sandbox-cubelet.service || return 1
            wait_for_services || return 1
            cleanup_sandboxes || return 1
            sleep 3
        fi
    fi

    after_sandboxes=$(sandbox_count) || return 1
    after_shims=$(shim_count)
    after_tasks=$(task_count)
    printf 'sandboxes=%s\nshims=%s\ntasks=%s\n' \
        "$after_sandboxes" "$after_shims" "$after_tasks" \
        >"$EVIDENCE_DIR/$label.after.txt"
    [[ "$after_sandboxes" == 0 && "$after_shims" == 0 && "$after_tasks" == 0 ]]
}

wait_empty_gate() {
    local label=$1
    local stable=0 attempt sandboxes shims tasks total in_use
    : >"$EVIDENCE_DIR/$label.gate.log"
    for attempt in $(seq 1 180); do
        sandboxes=$(sandbox_count 2>/dev/null || printf -- -1)
        shims=$(shim_count)
        tasks=$(task_count)
        total=$(tap_total)
        in_use=$(tap_in_use)
        printf '%s attempt=%s sandboxes=%s shims=%s tasks=%s tap_total=%s tap_in_use=%s\n' \
            "$(date -Is)" "$attempt" "$sandboxes" "$shims" "$tasks" "$total" "$in_use" \
            >>"$EVIDENCE_DIR/$label.gate.log"
        if wait_for_services && [[ "$sandboxes" == 0 && "$shims" == 0 && "$tasks" == 0 &&
            "$total" -ge "$TAP_TARGET" && "$in_use" == 0 ]]; then
            stable=$((stable + 1))
            [[ "$stable" -ge 3 ]] && return 0
        else
            stable=0
        fi
        sleep 2
    done
    return 1
}

capture_state() {
    local path=$1
    {
        printf 'timestamp=%s\n' "$(date -Is)"
        printf 'sandboxes=%s\n' "$(sandbox_count 2>/dev/null || printf -- -1)"
        printf 'shims=%s\n' "$(shim_count)"
        printf 'tasks=%s\n' "$(task_count)"
        printf 'tap_total=%s\n' "$(tap_total)"
        printf 'tap_in_use=%s\n' "$(tap_in_use)"
        printf 'mem_available_kib=%s\n' "$(mem_available_kib)"
        printf 'cubelet=%s\n' "$(systemctl is-active cube-sandbox-cubelet.service 2>/dev/null || true)"
        printf 'network_agent=%s\n' "$(systemctl is-active cube-sandbox-network-agent.service 2>/dev/null || true)"
        printf 'cubeapi_health='; curl -fsS --max-time 3 "$API_URL/cubeapi/v1/health" || true; printf '\n'
        printf 'network_health='; curl -fsS --max-time 3 http://127.0.0.1:19090/healthz || true; printf '\n'
        free -b
        df -B1 /data
    } >"$path"
}

cleanup_orphan_shims_with_live_tasks() {
    local label=$1
    local pid args id namespace attempt live
    local -a pids=()

    while read -r pid args; do
        id=$(sed -n 's/.* -id \([^ ]*\).*/\1/p' <<<"$args")
        namespace=$(sed -n 's/.* -namespace \([^ ]*\).*/\1/p' <<<"$args")
        [[ -n "$id" ]] || continue
        if [[ ! -d "$TASK_DIR/$namespace/$id" ]]; then
            printf 'pid=%s namespace=%s id=%s\n' "$pid" "$namespace" "$id" \
                >>"$DENSITY_DIR/$label.orphan-shims.txt"
            pids+=("$pid")
        fi
    done < <(ps -eo pid=,args= | awk -v shim="$SHIM_BIN" \
        '$2 == shim {pid=$1; $1=""; sub(/^ +/, ""); print pid, $0}')

    printf 'orphan_count=%s\n' "${#pids[@]}" >>"$DENSITY_DIR/$label.orphan-shims.txt"
    if ((${#pids[@]})); then
        kill -TERM "${pids[@]}" 2>/dev/null || true
        for attempt in $(seq 1 10); do
            live=0
            for pid in "${pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && live=$((live + 1))
            done
            [[ "$live" == 0 ]] && break
            sleep 1
        done
        for pid in "${pids[@]}"; do
            kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
        done
        sleep 2
    fi
}

run_cube_bench() {
    local report=$1 output=$2 concurrency=$3 total=$4 warmup=$5
    printf '%q ' "$BENCH" -api-url "$API_URL" -api-key "$API_KEY" \
        -template "$TEMPLATE_ID" -c "$concurrency" -n "$total" -w "$warmup" \
        -m create-only -no-tui -o "$report" >"${report%.json}.cmd"
    printf '\n' >>"${report%.json}.cmd"
    timeout --signal=TERM --kill-after=30s 30m \
        "$BENCH" -api-url "$API_URL" -api-key "$API_KEY" \
        -template "$TEMPLATE_ID" -c "$concurrency" -n "$total" -w "$warmup" \
        -m create-only -no-tui -o "$report" >"$output" 2>&1
}

write_startup_summary() {
    local name=$1 concurrency=$2 total=$3 rc=$4 report=$5
    if [[ -s "$report" ]] && jq -e . "$report" >/dev/null 2>&1; then
        jq --arg name "$name" --argjson concurrency "$concurrency" \
            --argjson requests "$total" --argjson bench_exit "$rc" \
            '{case:$name, concurrency:$concurrency, requests:$requests,
              bench_exit:$bench_exit,
              successful:(.summary.successful // 0), errors:(.summary.errors // 0),
              success_rate:(.summary.success_rate // 0),
              avg_ms:(.create.avg // 0), min_ms:(.create.min // 0),
              p95_ms:(.create.p95 // 0), max_ms:(.create.max // 0),
              total_time_s:(.summary.total_time_s // 0),
              per_sandbox_ms:(((.summary.total_time_s // 0) * 1000) / $requests),
              throughput_qps:(.summary.throughput_qps // 0)}' \
            "$report" >"$STARTUP_DIR/$name.summary.json"
    else
        jq -n --arg name "$name" --argjson concurrency "$concurrency" \
            --argjson requests "$total" --argjson bench_exit "$rc" \
            '{case:$name, concurrency:$concurrency, requests:$requests,
              bench_exit:$bench_exit, successful:0, errors:$requests,
              success_rate:0, avg_ms:0, min_ms:0, p95_ms:0, max_ms:0,
              total_time_s:0, per_sandbox_ms:0, throughput_qps:0}' \
            >"$STARTUP_DIR/$name.summary.json"
    fi
}

run_startup_case() {
    local name=$1 concurrency=$2 total=$3
    local report="$STARTUP_DIR/$name.json"
    local output="$STARTUP_DIR/$name.log"
    local since rc successful errors

    recover_empty_runtime "$name-pre" && wait_empty_gate "$name-pre" || {
        log "STARTUP_ABORT name=$name reason=precondition_failed"
        FAILED=1
        return 1
    }
    capture_state "$STARTUP_DIR/$name.before.txt"
    since=$(date -Is)
    log "STARTUP_BEGIN name=$name concurrency=$concurrency requests=$total warmup=3"
    run_cube_bench "$report" "$output" "$concurrency" "$total" 3
    rc=$?
    printf '%s\n' "$rc" >"$STARTUP_DIR/$name.exit"
    capture_state "$STARTUP_DIR/$name.before-cleanup.txt"
    sandbox_json >"$STARTUP_DIR/$name.sandboxes-before-cleanup.json" || true
    pgrep -fa "^${SHIM_BIN} " >"$STARTUP_DIR/$name.shims-before-cleanup.txt" || true
    journalctl -u cube-sandbox-cubelet.service --since "$since" --no-pager \
        >"$STARTUP_DIR/$name.cubelet.log"
    journalctl -u cube-sandbox-network-agent.service --since "$since" --no-pager \
        >"$STARTUP_DIR/$name.network-agent.log"
    write_startup_summary "$name" "$concurrency" "$total" "$rc" "$report"
    successful=$(jq -r '.successful' "$STARTUP_DIR/$name.summary.json")
    errors=$(jq -r '.errors' "$STARTUP_DIR/$name.summary.json")

    recover_empty_runtime "$name-post" && wait_empty_gate "$name-post" || {
        log "STARTUP_ABORT name=$name reason=post_cleanup_failed"
        FAILED=1
        return 1
    }
    capture_state "$STARTUP_DIR/$name.after.txt"
    log "STARTUP_END name=$name exit=$rc successful=$successful errors=$errors"
    if [[ "$rc" != 0 || "$successful" != "$total" || "$errors" != 0 ]]; then
        FAILED=1
    fi
    sleep 5
    return 0
}

run_startup_until_success() {
    local base=$1 concurrency=$2 total=$3
    local attempt=1 name before_failed successful errors bench_exit

    while true; do
        name="$base-attempt-$attempt"
        before_failed=$FAILED
        run_startup_case "$name" "$concurrency" "$total" || true
        if [[ -s "$STARTUP_DIR/$name.summary.json" ]]; then
            successful=$(jq -r '.successful' "$STARTUP_DIR/$name.summary.json")
            errors=$(jq -r '.errors' "$STARTUP_DIR/$name.summary.json")
            bench_exit=$(jq -r '.bench_exit' "$STARTUP_DIR/$name.summary.json")
        else
            successful=0
            errors=$total
            bench_exit=1
        fi
        if [[ "$bench_exit" == 0 && "$successful" == "$total" && "$errors" == 0 ]]; then
            cp "$STARTUP_DIR/$name.summary.json" "$STARTUP_DIR/$base.selected.json"
            printf '%s\n' "$name" >"$STARTUP_DIR/$base.selected-attempt.txt"
            FAILED=$before_failed
            log "STARTUP_ACCEPT base=$base attempt=$attempt"
            return 0
        fi
        FAILED=$before_failed
        log "STARTUP_RETRY base=$base failed_attempt=$attempt"
        attempt=$((attempt + 1))
        sleep 10
    done
}

wait_density_state() {
    local expected=$1 label=$2
    local stable=0 attempt sandboxes in_use total
    : >"$DENSITY_DIR/$label.gate.log"
    for attempt in $(seq 1 90); do
        sandboxes=$(sandbox_count 2>/dev/null || printf -- -1)
        in_use=$(tap_in_use)
        total=$(tap_total)
        printf '%s attempt=%s expected=%s sandboxes=%s tap_total=%s tap_in_use=%s shims=%s tasks=%s\n' \
            "$(date -Is)" "$attempt" "$expected" "$sandboxes" "$total" "$in_use" \
            "$(shim_count)" "$(task_count)" >>"$DENSITY_DIR/$label.gate.log"
        if wait_for_services && [[ "$sandboxes" == "$expected" && "$in_use" == "$expected" &&
            "$total" -ge "$TAP_TARGET" ]]; then
            stable=$((stable + 1))
            [[ "$stable" -ge 3 ]] && return 0
        else
            stable=0
        fi
        sleep 2
    done
    return 1
}

record_density_point() {
    local target=$1 baseline_kib=$2
    local current_kib available_gib delta_kib per_vm_mib sandboxes shims tasks total in_use
    current_kib=$(mem_available_kib)
    sandboxes=$(sandbox_count)
    shims=$(shim_count)
    tasks=$(task_count)
    total=$(tap_total)
    in_use=$(tap_in_use)
    available_gib=$(awk -v k="$current_kib" 'BEGIN {printf "%.3f", k / 1024 / 1024}')
    delta_kib=$((baseline_kib - current_kib))
    per_vm_mib=$(awk -v d="$delta_kib" -v n="$target" \
        'BEGIN {if (n == 0) print 0; else printf "%.3f", d / 1024 / n}')
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$target" "$current_kib" "$available_gib" "$delta_kib" "$per_vm_mib" \
        "$sandboxes" "$shims" "$in_use" >>"$DENSITY_DIR/points.tsv"
    capture_state "$DENSITY_DIR/active-$target.state.txt"
    sandbox_json >"$DENSITY_DIR/active-$target.sandboxes.json"
    printf 'tap_total=%s\ntasks=%s\n' "$total" "$tasks" \
        >>"$DENSITY_DIR/active-$target.state.txt"
}

run_density_batch() {
    local target=$1 increment=$2
    local attempt missing current report output rc since successful errors

    attempt=1
    missing=$increment
    while [[ "$missing" -gt 0 && "$attempt" -le 5 ]]; do
        report="$DENSITY_DIR/to-$target-attempt-$attempt.json"
        output="$DENSITY_DIR/to-$target-attempt-$attempt.log"
        since=$(date -Is)
        log "DENSITY_BATCH_BEGIN target=$target attempt=$attempt requests=$missing concurrency=50"
        run_cube_bench "$report" "$output" 50 "$missing" 0
        rc=$?
        printf '%s\n' "$rc" >"$DENSITY_DIR/to-$target-attempt-$attempt.exit"
        journalctl -u cube-sandbox-cubelet.service --since "$since" --no-pager \
            >"$DENSITY_DIR/to-$target-attempt-$attempt.cubelet.log"
        cleanup_orphan_shims_with_live_tasks "to-$target-attempt-$attempt"
        if [[ -s "$report" ]]; then
            successful=$(jq -r '.summary.successful // 0' "$report")
            errors=$(jq -r '.summary.errors // 0' "$report")
        else
            successful=0
            errors=$missing
        fi
        current=$(sandbox_count 2>/dev/null || printf -- -1)
        log "DENSITY_BATCH_END target=$target attempt=$attempt exit=$rc successful=$successful errors=$errors active=$current"
        [[ "$current" =~ ^[0-9]+$ ]] || return 1
        if [[ "$current" -gt "$target" ]]; then
            log "DENSITY_ABORT target=$target reason=active_exceeds_target active=$current"
            return 1
        fi
        missing=$((target - current))
        attempt=$((attempt + 1))
    done
    [[ "$missing" == 0 ]]
}

run_density() {
    local baseline_kib target increment

    recover_empty_runtime density-pre && wait_empty_gate density-pre || {
        log "DENSITY_ABORT reason=precondition_failed"
        FAILED=1
        return 1
    }
    capture_state "$DENSITY_DIR/baseline.state.txt"
    baseline_kib=$(mem_available_kib)
    printf 'target\tmem_available_kib\tmem_available_gib\tdelta_kib\tper_vm_mib\tsandboxes\tshims\ttap_in_use\n' \
        >"$DENSITY_DIR/points.tsv"
    printf '0\t%s\t%s\t0\t0\t0\t0\t0\n' "$baseline_kib" \
        "$(awk -v k="$baseline_kib" 'BEGIN {printf "%.3f", k / 1024 / 1024}')" \
        >>"$DENSITY_DIR/points.tsv"

    while read -r target increment; do
        capture_state "$DENSITY_DIR/to-$target.before.txt"
        if [[ "$(mem_available_kib)" -lt 268435456 ]]; then
            log "DENSITY_ABORT target=$target reason=available_memory_below_256GiB"
            FAILED=1
            break
        fi
        if ! run_density_batch "$target" "$increment"; then
            log "DENSITY_ABORT target=$target reason=unable_to_reach_target"
            FAILED=1
            break
        fi
        if ! wait_density_state "$target" "active-$target"; then
            log "DENSITY_ABORT target=$target reason=state_gate_failed"
            FAILED=1
            break
        fi
        record_density_point "$target" "$baseline_kib"
        sleep 5
    done <<'EOF'
100 100
300 200
500 200
1000 500
EOF

    sandbox_json >"$DENSITY_DIR/final.sandboxes-before-cleanup.json" || true
    recover_empty_runtime density-post && wait_empty_gate density-post || {
        log "DENSITY_ABORT reason=post_cleanup_failed"
        FAILED=1
        return 1
    }
    capture_state "$DENSITY_DIR/final.state-after-cleanup.txt"
    log "DENSITY_END"
}

main() {
    local item name concurrency total
    local -a cases=()
    : >"$WORKDIR/run.log"
    {
        printf 'started_at=%s\n' "$(date -Is)"
        printf 'template_id=%s\n' "$TEMPLATE_ID"
        printf 'api_url=%s\n' "$API_URL"
        printf 'benchmark=%s\n' "$BENCH"
        printf 'tap_target=%s\n' "$TAP_TARGET"
        printf 'host_kernel=%s\n' "$(uname -r)"
    } >"$EVIDENCE_DIR/test-context.txt"

    if [[ "$RUN_STARTUP" == 1 ]]; then
        mapfile -t cases < <(printf '%s\n' "$CASE_MATRIX" | sed '/^[[:space:]]*$/d')
        for item in "${cases[@]}"; do
            read -r name concurrency total <<<"$item"
            if [[ "$RETRY_UNTIL_SUCCESS" == 1 ]]; then
                run_startup_until_success "$name" "$concurrency" "$total"
            else
                run_startup_case "$name" "$concurrency" "$total" || true
            fi
        done

        if [[ "$RETRY_UNTIL_SUCCESS" == 1 ]]; then
            jq -s '{cases:., total_requests:(map(.requests) | add),
                total_successful:(map(.successful) | add), total_errors:(map(.errors) | add)}' \
                "$STARTUP_DIR"/*.selected.json >"$STARTUP_DIR/aggregate.json"
        else
            jq -s '{cases:., total_requests:(map(.requests) | add),
                total_successful:(map(.successful) | add), total_errors:(map(.errors) | add)}' \
                "$STARTUP_DIR"/*.summary.json >"$STARTUP_DIR/aggregate.json"
        fi
        rg -i 'reset guest|guest time|timed out|timeout|failed to reset|reset.*failed' \
            "$STARTUP_DIR"/*.cubelet.log >"$STARTUP_DIR/reset-timeout-signatures.txt" || true
    fi

    if [[ "$RUN_DENSITY" == 1 ]]; then
        run_density
    fi

    printf 'finished_at=%s\nstatus=%s\n' "$(date -Is)" \
        "$([[ "$FAILED" == 0 ]] && printf complete || printf completed-with-errors)" \
        >"$WORKDIR/status.txt"
    find "$WORKDIR" -type f -print0 | sort -z | xargs -0 sha256sum >"$WORKDIR/SHA256SUMS"
    exit "$FAILED"
}

main "$@"
