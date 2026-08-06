#!/usr/bin/env bash
# Build multiple 1U-5U templates serially, then run an independent concurrent
# restore test for every template. Run this script on the CubeSandbox host.
set -uo pipefail

usage() {
    cat <<'EOF'
Usage: validate_aprmask_multi_resource_templates_65.sh EVIDENCE_DIR

Environment variables:
  API_URL                 Cube API URL (default: http://127.0.0.1:13000)
  API_KEY                 API bearer token (default: e2b_000000)
  IMAGE                   Template image
  CPU_UNITS               Space-separated CPU units (default: "1 2 3 4 5")
  MEMORY_MB               Memory for every template (default: 2000)
  TEMPLATES_PER_CPU       New templates per CPU setting (default: 5)
  ROUNDS                  Concurrent restore rounds (default: 6)
  REQUESTS_PER_TEMPLATE   Creates per template in each round (default: 50)
  GLOBAL_CONCURRENCY      Maximum simultaneous creates (default: 50)
  CREATE_TIMEOUT          Per-create timeout in seconds (default: 60)
  BUILD_TIMEOUT           Template build timeout in seconds (default: 900)
  TAP_WAIT_TIMEOUT        Seconds to wait for TAP pool recovery (default: 300)
  TAP_STABLE_SAMPLES      Consecutive healthy TAP samples (default: 3)
  EXISTING_TEMPLATES_TSV  Reuse a prior templates.tsv instead of rebuilding

Templates are built strictly one at a time. Restore rounds run one template at
a time, and run-created sandboxes and orphan shims are cleaned between rounds.
New templates are left in place. The script exits non-zero if any build or
restore fails, cleanup cannot reach zero, or an old-bug signature is found.
EOF
}

[[ ${1:-} == -h || ${1:-} == --help ]] && { usage; exit 0; }
[[ $# -eq 1 ]] || { usage >&2; exit 64; }

evidence_dir=$1
api_url=${API_URL:-http://127.0.0.1:13000}
api_key=${API_KEY:-e2b_000000}
image=${IMAGE:-192.168.25.65:2900/bench/sandbox-code:latest}
cpu_units=${CPU_UNITS:-1 2 3 4 5}
memory_mb=${MEMORY_MB:-2000}
templates_per_cpu=${TEMPLATES_PER_CPU:-5}
rounds=${ROUNDS:-6}
requests_per_template=${REQUESTS_PER_TEMPLATE:-50}
global_concurrency=${GLOBAL_CONCURRENCY:-50}
create_timeout=${CREATE_TIMEOUT:-60}
build_timeout=${BUILD_TIMEOUT:-900}
tap_wait_timeout=${TAP_WAIT_TIMEOUT:-300}
tap_stable_samples=${TAP_STABLE_SAMPLES:-3}
existing_templates_tsv=${EXISTING_TEMPLATES_TSV:-}
poll_interval=5
shim_log=/data/log/CubeShim/cube-shim-req.log
runtime_bin=/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime
network_agent_service=cube-sandbox-network-agent.service
network_agent_health=http://127.0.0.1:19090/healthz
network_agent_log=/data/log/network-agent/network-agent-req.log
cubelet_config=/usr/local/services/cubetoolbox/Cubelet/config/config.toml

mkdir -p "$evidence_dir" "$evidence_dir/build" "$evidence_dir/responses"
evidence_dir=$(realpath "$evidence_dir")
run_log=$evidence_dir/run.log
results_tsv=$evidence_dir/results.tsv
templates_tsv=$evidence_dir/templates.tsv
summary_tsv=$evidence_dir/summary.tsv
start_time=$(date -Is)
shim_log_start_lines=0
[[ -f $shim_log ]] && shim_log_start_lines=$(wc -l < "$shim_log")

exec > >(tee -a "$run_log") 2>&1
log() { printf '%s %s\n' "$(date -Is)" "$*"; }
die() { log "ABORT $*"; exit 1; }

require_uint() {
    local name=$1 value=$2
    [[ $value =~ ^[1-9][0-9]*$ ]] || die "$name must be a positive integer (got: $value)"
}

for pair in \
    "MEMORY_MB:$memory_mb" \
    "TEMPLATES_PER_CPU:$templates_per_cpu" \
    "ROUNDS:$rounds" \
    "REQUESTS_PER_TEMPLATE:$requests_per_template" \
    "GLOBAL_CONCURRENCY:$global_concurrency" \
    "CREATE_TIMEOUT:$create_timeout" \
    "BUILD_TIMEOUT:$build_timeout" \
    "TAP_WAIT_TIMEOUT:$tap_wait_timeout" \
    "TAP_STABLE_SAMPLES:$tap_stable_samples"; do
    require_uint "${pair%%:*}" "${pair#*:}"
done
for cpu in $cpu_units; do require_uint CPU_UNIT "$cpu"; done

for command in curl jq flock realpath sha256sum; do
    command -v "$command" >/dev/null || die "missing command: $command"
done

auth=(-H "Authorization: Bearer $api_key")
curl -fsS --max-time 10 "${auth[@]}" "$api_url/templates" >/dev/null || \
    die "Cube API is unavailable at $api_url"

curl -fsS --max-time 10 "${auth[@]}" "$api_url/sandboxes" \
    | jq -r '.[] | .sandboxID // .sandbox_id // .id // empty' \
    > "$evidence_dir/baseline-sandbox-ids.txt" || die "cannot record baseline sandboxes"
pgrep -f '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' \
    > "$evidence_dir/baseline-shim-pids.txt" || true

{
    printf 'start_time\t%s\n' "$start_time"
    printf 'host\t%s\n' "$(hostname)"
    printf 'kernel\t%s\n' "$(uname -r)"
    printf 'runtime_sha256\t%s\n' "$(sha256sum "$runtime_bin" 2>/dev/null | awk '{print $1}')"
    printf 'runtime_version\t%s\n' "$("$runtime_bin" --version 2>&1 | head -1)"
    printf 'api_url\t%s\n' "$api_url"
    printf 'image\t%s\n' "$image"
    printf 'cpu_units\t%s\n' "$cpu_units"
    printf 'memory_mb\t%s\n' "$memory_mb"
    printf 'templates_per_cpu\t%s\n' "$templates_per_cpu"
    printf 'rounds\t%s\n' "$rounds"
    printf 'requests_per_template\t%s\n' "$requests_per_template"
    printf 'global_concurrency\t%s\n' "$global_concurrency"
    printf 'tap_wait_timeout\t%s\n' "$tap_wait_timeout"
    printf 'tap_stable_samples\t%s\n' "$tap_stable_samples"
    printf 'existing_templates_tsv\t%s\n' "$existing_templates_tsv"
} > "$evidence_dir/environment.tsv"
uname -a > "$evidence_dir/uname.txt"
free -h > "$evidence_dir/free-before.txt"
df -h > "$evidence_dir/df-before.txt"

printf 'cpu_unit\tcpu_millicores\tmemory_mb\ttemplate_index\ttemplate_id\tstatus\terror\n' > "$templates_tsv"
declare -a template_ids=()
declare -a template_cpus=()

tap_init_num=$(awk '
    /^[[:space:]]*\[/ {
        in_network = ($0 ~ /^[[:space:]]*\[plugins\."io\.cubelet\.internal\.v1\.network"\][[:space:]]*$/)
    }
    in_network && /^[[:space:]]*tap_init_num[[:space:]]*=/ {
        line = $0
        sub(/#.*/, "", line)
        sub(/^[^=]*=/, "", line)
        gsub(/[[:space:]]/, "", line)
        print line
        exit
    }
' "$cubelet_config")
require_uint TAP_INIT_NUM "$tap_init_num"
printf 'tap_init_num\t%s\n' "$tap_init_num" >> "$evidence_dir/environment.tsv"

tap_link_count() {
    ip -o link show | awk -F': ' '$2 ~ /^z/ {count++} END {print count+0}'
}

latest_tap_pool_status() {
    tail -n 4000 "$network_agent_log" | jq -r '
        select((.LogContent // "") |
            test("tap pooled|tap dequeued|marked abnormal|quarantined|refill")) |
        .LogContent
    ' 2>/dev/null | tail -n 1
}

tap_status_value() {
    local key=$1 status=$2
    sed -n "s/.* ${key}=\([0-9][0-9]*\).*/\1/p" <<< "$status"
}

wait_for_clean_tap_inventory() {
    local label=$1 attempt stable=0 links status pool abnormal quarantined
    for attempt in $(seq 1 "$tap_wait_timeout"); do
        links=$(tap_link_count)
        status=$(latest_tap_pool_status)
        pool=$(tap_status_value pool "$status")
        abnormal=$(tap_status_value abnormal "$status")
        quarantined=$(tap_status_value quarantined "$status")
        if systemctl is-active --quiet "$network_agent_service" &&
            curl -fsS --max-time 2 "$network_agent_health" >/dev/null &&
            [[ $links =~ ^[0-9]+$ && $pool =~ ^[0-9]+$ &&
                $abnormal =~ ^[0-9]+$ && $quarantined =~ ^[0-9]+$ ]] &&
            [[ $links == "$tap_baseline_links" && $pool == "$tap_baseline_pool" &&
                $abnormal == 0 && $quarantined == 0 ]]; then
            stable=$((stable + 1))
            if ((stable >= tap_stable_samples)); then
                log "TAP_READY label=$label links=$links pool=$pool abnormal=$abnormal quarantined=$quarantined"
                return 0
            fi
        else
            stable=0
        fi
        if ((attempt == 1 || attempt % 15 == 0)); then
            log "TAP_WAIT label=$label attempt=$attempt links=$links pool=${pool:-unknown} abnormal=${abnormal:-unknown} quarantined=${quarantined:-unknown}"
        fi
        sleep 1
    done
    log "TAP_TIMEOUT label=$label links=${links:-unknown} pool=${pool:-unknown} abnormal=${abnormal:-unknown} quarantined=${quarantined:-unknown}"
    return 1
}

tap_baseline_links=$(tap_link_count)
tap_baseline_status=$(latest_tap_pool_status)
tap_baseline_pool=$(tap_status_value pool "$tap_baseline_status")
tap_baseline_abnormal=$(tap_status_value abnormal "$tap_baseline_status")
tap_baseline_quarantined=$(tap_status_value quarantined "$tap_baseline_status")
[[ $tap_baseline_links == "$tap_init_num" ]] || \
    die "TAP link baseline is not ready: links=$tap_baseline_links target=$tap_init_num"
[[ $tap_baseline_pool =~ ^[1-9][0-9]*$ && $tap_baseline_abnormal == 0 &&
    $tap_baseline_quarantined == 0 ]] || \
    die "TAP pool baseline is unhealthy: $tap_baseline_status"
{
    printf 'tap_baseline_links\t%s\n' "$tap_baseline_links"
    printf 'tap_baseline_pool\t%s\n' "$tap_baseline_pool"
} >> "$evidence_dir/environment.tsv"

template_status() {
    curl -fsS --max-time 15 "${auth[@]}" "$api_url/templates" 2>/dev/null \
        | jq -r --arg tid "$1" \
            '.[] | select(.templateID == $tid) | [(.status // "UNKNOWN"), (.lastError // "")] | @tsv'
}

if [[ -n $existing_templates_tsv ]]; then
    [[ -f $existing_templates_tsv ]] || die "missing EXISTING_TEMPLATES_TSV: $existing_templates_tsv"
    cp "$existing_templates_tsv" "$templates_tsv"
    while IFS=$'\t' read -r cpu _ _ _ tid status _; do
        [[ $cpu == cpu_unit || $status != READY || -z $tid ]] && continue
        template_ids+=("$tid")
        template_cpus+=("$cpu")
    done < "$templates_tsv"
    log "BUILD reused templates file=$existing_templates_tsv ready=${#template_ids[@]}"
else
  log "BUILD creating 1U-5U templates strictly serially: per_cpu=$templates_per_cpu image=$image"
  for cpu in $cpu_units; do
    cpu_millicores=$((cpu * 1000))
    for index in $(seq 1 "$templates_per_cpu"); do
        tag=${cpu}u-t${index}
        response_file=$evidence_dir/build/submit-$tag.json
        http_file=$evidence_dir/build/submit-$tag.http
        curl_rc=0
        curl -sS --max-time 30 -o "$response_file" -w '%{http_code}\n' \
            -X POST "${auth[@]}" -H 'Content-Type: application/json' \
            -d "{\"image\":\"$image\",\"cpu\":$cpu_millicores,\"memory\":$memory_mb,\"writableLayerSize\":\"1G\"}" \
            "$api_url/templates" > "$http_file" || curl_rc=$?
        tid=$(jq -r '.templateID // .template_id // empty' "$response_file" 2>/dev/null)
        if [[ $curl_rc -ne 0 || -z $tid ]]; then
            error=$(jq -r '.message // .error // "template submission failed"' "$response_file" 2>/dev/null)
            printf '%s\t%s\t%s\t%s\t\tSUBMIT_FAILED\t%s\n' \
                "$cpu" "$cpu_millicores" "$memory_mb" "$index" "${error//$'\t'/ }" >> "$templates_tsv"
            log "BUILD $tag SUBMIT_FAILED curl_rc=$curl_rc"
            continue
        fi
        log "BUILD $tag submitted template=$tid"
        deadline=$((SECONDS + build_timeout))
        status=UNKNOWN
        error=''
        while ((SECONDS < deadline)); do
            state=$(template_status "$tid")
            if [[ $state == *$'\t'* ]]; then
                status=${state%%$'\t'*}
                error=${state#*$'\t'}
            else
                status=${state:-UNKNOWN}
                error=''
            fi
            [[ $status == READY || $status == FAILED ]] && break
            sleep "$poll_interval"
        done
        if [[ $status != READY && $status != FAILED ]]; then
            status=TIMEOUT
            error="template did not finish within ${build_timeout}s"
        fi
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$cpu" "$cpu_millicores" "$memory_mb" "$index" "$tid" "$status" \
            "${error//$'\t'/ }" >> "$templates_tsv"
        if [[ $status == READY ]]; then
            template_ids+=("$tid")
            template_cpus+=("$cpu")
        fi
        log "BUILD $tag template=$tid status=$status error=${error:0:160}"
    done
  done
fi

expected_templates=$(wc -w <<< "$cpu_units")
expected_templates=$((expected_templates * templates_per_cpu))
((${#template_ids[@]} == expected_templates)) || \
    log "BUILD WARNING ready=${#template_ids[@]} expected=$expected_templates"
((${#template_ids[@]})) || die "no READY templates"

printf 'request_id\tround\tcpu_unit\ttemplate_id\tcurl_rc\thttp_code\telapsed_seconds\tstatus\tsignature\tsandbox_id\tdelete_status\n' > "$results_tsv"

cleanup_resources() {
    local label=$1 cleanup_deadline sid pid remaining_sandboxes remaining_shims
    local tap_status tap_links tap_pool tap_abnormal tap_quarantined tap_ready=0
    local current_ids=$evidence_dir/cleanup-$label-sandbox-ids.txt
    local remove_ids=$evidence_dir/cleanup-$label-remove-ids.txt
    curl -fsS --max-time 15 "${auth[@]}" "$api_url/sandboxes" \
        | jq -r '.[] | .sandboxID // .sandbox_id // .id // empty' > "$current_ids" || return 1
    grep -Fvx -f "$evidence_dir/baseline-sandbox-ids.txt" "$current_ids" > "$remove_ids" || true
    while read -r sid; do
        [[ -z $sid ]] && continue
        curl -sS --max-time 30 -o "$evidence_dir/responses/cleanup-$label-$sid.json" \
            -X DELETE "${auth[@]}" "$api_url/sandboxes/$sid" || true
    done < "$remove_ids"

    cleanup_deadline=$((SECONDS + 45))
    while ((SECONDS < cleanup_deadline)); do
        curl -fsS --max-time 10 "${auth[@]}" "$api_url/sandboxes" \
            | jq -r '.[] | .sandboxID // .sandbox_id // .id // empty' > "$current_ids" || true
        grep -Fvx -f "$evidence_dir/baseline-sandbox-ids.txt" "$current_ids" > "$remove_ids" || true
        [[ ! -s $remove_ids ]] && break
        sleep 1
    done

    # Any shim absent from the baseline and still alive after sandbox deletion
    # is a failed-create orphan owned by this validation run.
    while read -r pid; do
        [[ -z $pid ]] && continue
        grep -Fxq "$pid" "$evidence_dir/baseline-shim-pids.txt" && continue
        kill -TERM "$pid" 2>/dev/null || true
    done < <(pgrep -f '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true)
    sleep 2
    while read -r pid; do
        [[ -z $pid ]] && continue
        grep -Fxq "$pid" "$evidence_dir/baseline-shim-pids.txt" && continue
        kill -KILL "$pid" 2>/dev/null || true
    done < <(pgrep -f '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true)

    remaining_sandboxes=$(wc -l < "$remove_ids")
    remaining_shims=0
    while read -r pid; do
        [[ -z $pid ]] && continue
        grep -Fxq "$pid" "$evidence_dir/baseline-shim-pids.txt" || remaining_shims=$((remaining_shims + 1))
    done < <(pgrep -f '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true)
    if wait_for_clean_tap_inventory "$label"; then tap_ready=1; fi
    tap_status=$(latest_tap_pool_status)
    tap_links=$(tap_link_count)
    tap_pool=$(tap_status_value pool "$tap_status")
    tap_abnormal=$(tap_status_value abnormal "$tap_status")
    tap_quarantined=$(tap_status_value quarantined "$tap_status")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$label" "$remaining_sandboxes" "$remaining_shims" \
        "$tap_ready" "$tap_links" "${tap_pool:-}" "${tap_abnormal:-}" "${tap_quarantined:-}" \
        >> "$evidence_dir/cleanup-summary.tsv"
    log "CLEANUP label=$label sandboxes=$remaining_sandboxes shims=$remaining_shims tap_ready=$tap_ready links=$tap_links pool=${tap_pool:-unknown}"
    [[ $remaining_sandboxes -eq 0 && $remaining_shims -eq 0 && $tap_ready -eq 1 ]]
}

printf 'label\tremaining_run_sandboxes\tremaining_run_shims\ttap_ready\ttap_links\ttap_pool\ttap_abnormal\ttap_quarantined\n' > "$evidence_dir/cleanup-summary.tsv"

classify_response() {
    local response_file=$1
    if grep -qi 'reset guest time failed' "$response_file"; then printf old_reset_guest_time
    elif grep -qiE 'Boot vm failed|failed to (boot|start|resume|restore) (the )?vm|vm has not been booted' "$response_file"; then printf vm_boot_failed
    elif grep -qi 'reset reseed random dev failed' "$response_file"; then printf reset_reseed_failed
    elif grep -qiE 'no more resource|resource exhausted|PortBindingFailed' "$response_file"; then printf resource_exhausted
    elif grep -qiE 'timed out|timeout|context deadline' "$response_file"; then printf timeout
    elif grep -qiE 'HTTP transport error|connection refused|connection reset' "$response_file"; then printf transport
    else printf other
    fi
}

run_one() {
    local request_id=$1 round=$2 cpu=$3 tid=$4
    local response_file=$evidence_dir/responses/create-$request_id.json
    local meta_file=$evidence_dir/responses/create-$request_id.meta
    local curl_rc=0 http_code elapsed sid status signature delete_status
    curl -sS --max-time "$create_timeout" -o "$response_file" -w '%{http_code}\t%{time_total}\n' \
        -X POST "${auth[@]}" -H 'Content-Type: application/json' \
        -d "{\"templateID\":\"$tid\"}" "$api_url/sandboxes" > "$meta_file" || curl_rc=$?
    read -r http_code elapsed < "$meta_file" || true
    http_code=${http_code:-000}
    elapsed=${elapsed:-0}
    sid=$(jq -r '.sandboxID // .sandbox_id // .id // empty' "$response_file" 2>/dev/null)
    delete_status=not_applicable
    if [[ $curl_rc -eq 0 && $http_code =~ ^2 && -n $sid ]]; then
        status=PASS
        signature=none
        delete_code=$(curl -sS --max-time 30 -o "$evidence_dir/responses/delete-$request_id.json" \
            -w '%{http_code}' -X DELETE "${auth[@]}" "$api_url/sandboxes/$sid" 2>/dev/null) || true
        if [[ $delete_code =~ ^2 ]]; then delete_status=PASS; else delete_status="FAIL:${delete_code:-000}"; fi
    else
        status=FAIL
        signature=$(classify_response "$response_file")
    fi
    {
        flock 9
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$request_id" "$round" "$cpu" "$tid" "$curl_rc" "$http_code" "$elapsed" \
            "$status" "$signature" "$sid" "$delete_status" >&9
    } 9>> "$results_tsv"
}

request_number=0
cleanup_failures=0
wait_for_clean_tap_inventory preflight || die "TAP pool did not recover before restore validation"
for array_index in "${!template_ids[@]}"; do
    tid=${template_ids[$array_index]}
    cpu=${template_cpus[$array_index]}
    for round in $(seq 1 "$rounds"); do
        log "RESTORE template=$tid cpu=${cpu}U round=$round requests=$requests_per_template concurrency=$global_concurrency"
        declare -a worker_pids=()
        for request_index in $(seq 1 "$requests_per_template"); do
            request_number=$((request_number + 1))
            request_id=$(printf 'r%02d-q%05d-%su-t%s' "$round" "$request_number" \
                "$cpu" "$request_index")
            run_one "$request_id" "$round" "$cpu" "$tid" &
            worker_pids+=("$!")
            while (($(jobs -rp | wc -l) >= global_concurrency)); do wait -n || true; done
        done
        for worker_pid in "${worker_pids[@]}"; do
            wait "$worker_pid" 2>/dev/null || true
        done
        unset worker_pids
        round_pass=$(awk -F '\t' -v r="$round" -v t="$tid" \
            'NR > 1 && $2 == r && $4 == t && $8 == "PASS" {n++} END {print n+0}' "$results_tsv")
        round_fail=$(awk -F '\t' -v r="$round" -v t="$tid" \
            'NR > 1 && $2 == r && $4 == t && $8 == "FAIL" {n++} END {print n+0}' "$results_tsv")
        cleanup_resources "${cpu}u-${tid}-r${round}" || cleanup_failures=$((cleanup_failures + 1))
        log "RESTORE template=$tid cpu=${cpu}U round=$round complete pass=$round_pass fail=$round_fail"
    done
done

{
    printf 'cpu_unit\ttemplate_id\ttotal\tpass\tfail\told_reset_guest_time\tvm_boot_failed\treset_reseed_failed\tresource_exhausted\ttimeout\ttransport\tother\n'
    for array_index in "${!template_ids[@]}"; do
        tid=${template_ids[$array_index]}
        cpu=${template_cpus[$array_index]}
        awk -F '\t' -v cpu="$cpu" -v tid="$tid" '
            BEGIN { OFS="\t" }
            NR > 1 && $4 == tid {
                total++
                if ($8 == "PASS") pass++; else fail++
                signatures[$9]++
            }
            END {
                print cpu, tid, total+0, pass+0, fail+0,
                    signatures["old_reset_guest_time"]+0,
                    signatures["vm_boot_failed"]+0,
                    signatures["reset_reseed_failed"]+0,
                    signatures["resource_exhausted"]+0,
                    signatures["timeout"]+0,
                    signatures["transport"]+0,
                    signatures["other"]+0
            }' "$results_tsv"
    done
} > "$summary_tsv"

if [[ -f $shim_log ]]; then
    tail -n "+$((shim_log_start_lines + 1))" "$shim_log" > "$evidence_dir/cube-shim-req.delta.log" 2>/dev/null || true
else
    : > "$evidence_dir/cube-shim-req.delta.log"
fi
dmesg --since "$start_time" > "$evidence_dir/dmesg.delta.log" 2>/dev/null || dmesg > "$evidence_dir/dmesg.final.log" 2>/dev/null || true
free -h > "$evidence_dir/free-after.txt"
df -h > "$evidence_dir/df-after.txt"
curl -fsS --max-time 15 "${auth[@]}" "$api_url/sandboxes" > "$evidence_dir/sandboxes-after.json" || true

total=$(awk -F '\t' 'NR > 1 {n++} END {print n+0}' "$results_tsv")
pass=$(awk -F '\t' 'NR > 1 && $8 == "PASS" {n++} END {print n+0}' "$results_tsv")
fail=$(awk -F '\t' 'NR > 1 && $8 == "FAIL" {n++} END {print n+0}' "$results_tsv")
reset_api=$(awk -F '\t' 'NR > 1 && $9 == "old_reset_guest_time" {n++} END {print n+0}' "$results_tsv")
reset_log=$(grep -ci 'reset guest time failed' "$evidence_dir/cube-shim-req.delta.log" 2>/dev/null || true)
rcu_stall=$(grep -ciE 'rcu.*stall|rcu_sched kthread starved|Possible timer handling issue' "$evidence_dir/dmesg.delta.log" 2>/dev/null || true)
boot_log=$(grep -ciE 'Boot vm failed|failed to (boot|start|resume|restore) (the )?vm' "$evidence_dir/cube-shim-req.delta.log" 2>/dev/null || true)
build_fail=$(awk -F '\t' 'NR > 1 && $6 != "READY" {n++} END {print n+0}' "$templates_tsv")

{
    printf 'metric\tvalue\n'
    printf 'templates_expected\t%s\n' "$expected_templates"
    printf 'templates_ready\t%s\n' "${#template_ids[@]}"
    printf 'template_build_failures\t%s\n' "$build_fail"
    printf 'cleanup_failures\t%s\n' "$cleanup_failures"
    printf 'restore_total\t%s\n' "$total"
    printf 'restore_pass\t%s\n' "$pass"
    printf 'restore_fail\t%s\n' "$fail"
    printf 'api_reset_guest_time_failed\t%s\n' "$reset_api"
    printf 'shim_log_reset_guest_time_failed\t%s\n' "$reset_log"
    printf 'shim_log_vm_boot_failed\t%s\n' "$boot_log"
    printf 'dmesg_rcu_stall_signatures\t%s\n' "$rcu_stall"
} > "$evidence_dir/totals.tsv"

log "RESULT templates=${#template_ids[@]}/$expected_templates restore_pass=$pass/$total restore_fail=$fail reset_api=$reset_api reset_log=$reset_log vm_boot_log=$boot_log rcu_stall=$rcu_stall"
if ((build_fail || cleanup_failures || fail || reset_api || reset_log || boot_log || rcu_stall)); then
    log "VERDICT FAIL"
    exit 1
fi
log "VERDICT PASS: pre-fix error signatures were not reproduced"
