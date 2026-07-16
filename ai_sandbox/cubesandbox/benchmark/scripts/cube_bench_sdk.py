#!/usr/bin/env python3
"""Reusable CubeSandbox benchmark runner using the E2B-compatible SDK.

Dependencies:

    pip install e2b-code-interpreter

Required environment or CLI options:

    E2B_API_URL=http://<cubeapi-host>:3000
    E2B_API_KEY=e2b_000000
    CUBE_TEMPLATE_ID=<template-id>

If CubeProxy uses Cube's mkcert CA, also set:

    SSL_CERT_FILE=/path/to/rootCA.pem

or pass:

    --ssl-cert-file /path/to/rootCA.pem
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tarfile
import time
from pathlib import Path
from typing import Any


Case = tuple[str, str, int]


GO_BENCH_DIRECT_SCRIPT = r"""set -euo pipefail
if grep -q "GO_BENCH_DISABLE_PERF" "$(command -v run-benchmark)" 2>/dev/null; then
  exec run-benchmark go-benchmark
fi

OUT_DIR="${CUBE_BENCH_OUT_DIR:-/tmp/cube-bench-results}"
repeats="${GO_BENCH_REPEATS:-1}"
raw_cases="${GO_BENCH_CASES:-build,http,json,garbage}"
raw_cases="${raw_cases//,/ }"
mkdir -p "${OUT_DIR}"
perf_shim_dir=""
if [[ "${GO_BENCH_DISABLE_PERF:-1}" == "1" ]]; then
  perf_shim_dir="$(mktemp -d)"
  cat >"${perf_shim_dir}/perf" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  record)
    shift
    while (($#)); do
      case "$1" in
        -o|--output)
          shift 2
          ;;
        --output=*)
          shift
          ;;
        --)
          shift
          break
          ;;
        -*)
          shift
          ;;
        *)
          break
          ;;
      esac
    done
    if (($#)); then
      exec "$@"
    fi
    ;;
  report)
    exit 0
    ;;
esac
EOF
  chmod +x "${perf_shim_dir}/perf"
fi
global_total=0
global_count=0
echo "[go-benchmark] upstream=golang.org/x/benchmarks cases=${raw_cases} repeats=${repeats} mode=direct disable-perf=${GO_BENCH_DISABLE_PERF:-1}"
for case_name in ${raw_cases}; do
  case "${case_name}" in
    build|http|json|garbage) ;;
    *) echo "[go-benchmark] invalid GO_BENCH_CASES item: ${case_name}" >&2; exit 2 ;;
  esac
  case_total=0
  case_count=0
  for repeat_idx in $(seq 1 "${repeats}"); do
    log="${OUT_DIR}/go-${case_name}-${repeat_idx}.log"
    echo "[go-benchmark] running ${case_name} repeat=${repeat_idx}"
    if [[ "${case_name}" == "build" && -n "${perf_shim_dir}" ]]; then
      PATH="${perf_shim_dir}:${PATH}" "/opt/cube-bench/bin/go-upstream/${case_name}" | tee "${log}"
    else
      "/opt/cube-bench/bin/go-upstream/${case_name}" | tee "${log}"
    fi
    value="$(awk '/^Benchmark/ {for (i=1; i<NF; i++) if ($(i+1) == "ns/op") {print $i; exit}}' "${log}" || true)"
    if [[ "${value}" =~ ^[0-9.]+$ ]]; then
      case_total="$(awk -v a="${case_total}" -v b="${value}" 'BEGIN {printf "%.6f", a+b}')"
      case_count=$((case_count + 1))
      global_total="$(awk -v a="${global_total}" -v b="${value}" 'BEGIN {printf "%.6f", a+b}')"
      global_count=$((global_count + 1))
    fi
  done
  if (( case_count > 0 )); then
    awk -v name="${case_name}" -v total="${case_total}" -v count="${case_count}" \
      'BEGIN {printf "{\"benchmark\":\"go-%s-average\",\"case\":\"%s\",\"value\":%.6f,\"unit\":\"ns/op\",\"samples\":%d}\n", name, name, total/count, count}'
  fi
done
if (( global_count > 0 )); then
  awk -v total="${global_total}" -v count="${global_count}" \
    'BEGIN {printf "{\"benchmark\":\"go-benchmark-average\",\"value\":%.6f,\"unit\":\"ns/op\",\"samples\":%d}\n", total/count, count}'
fi
if [[ -n "${perf_shim_dir}" ]]; then
  rm -rf "${perf_shim_dir}"
fi"""


def go_benchmark_command(repeats: int) -> str:
    return (
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "GO_BENCH_CASES=build,http,json,garbage "
        "GO_BENCH_DISABLE_PERF=1 "
        f"GO_BENCH_REPEATS={repeats} "
        "bash <<'CUBE_GO_BENCH'\n"
        f"{GO_BENCH_DIRECT_SCRIPT}\n"
        "CUBE_GO_BENCH"
    )

SMOKE_CASES: list[Case] = [
    ("00-versions", "run-benchmark versions", 60),
    (
        "01-sysbench-memory-all",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_TIME=5 SYSBENCH_MEMORY_TOTAL_SIZE=10G "
        "SYSBENCH_MEMORY_BLOCK_SIZE=1K SYSBENCH_MEMORY_THREADS=2 "
        "run-benchmark sysbench-memory-all",
        180,
    ),
    (
        "02-sysbench-prime",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_TIME=5 SYSBENCH_MAX_PRIME=5000 SYSBENCH_THREADS=2 "
        "run-benchmark sysbench-prime",
        120,
    ),
    (
        "03-go-benchmark",
        go_benchmark_command(1),
        600,
    ),
    (
        "04-php-benchmark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PHPBENCH_ITERATIONS=100000 run-benchmark php-benchmark",
        300,
    ),
    (
        "05-python-benchmark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PYPERFORMANCE_BENCHMARKS=python_startup,json_dumps "
        "PYPERFORMANCE_MODE=fast run-benchmark python-benchmark",
        600,
    ),
    (
        "06-node-octane",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark node-octane",
        900,
    ),
    (
        "07-java-scimark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark java-scimark",
        300,
    ),
]

FORMAL_PRIME_MAX_VALUES = [1000, 2000, 3000, 5000, 10000, 20000, 30000, 50000, 100000]

FORMAL_CASES: list[Case] = [
    ("00-versions", "run-benchmark versions", 60),
    (
        "01-sysbench-memory-seq-read-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_THREADS=2 SYSBENCH_MEMORY_BLOCK_SIZE=1G "
        "SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_TIME=30 "
        "SYSBENCH_MEMORY_OPER=read SYSBENCH_MEMORY_ACCESS_MODE=seq "
        "run-benchmark sysbench-memory",
        900,
    ),
    (
        "01-sysbench-memory-seq-write-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_THREADS=2 SYSBENCH_MEMORY_BLOCK_SIZE=1G "
        "SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_TIME=30 "
        "SYSBENCH_MEMORY_OPER=write SYSBENCH_MEMORY_ACCESS_MODE=seq "
        "run-benchmark sysbench-memory",
        900,
    ),
    (
        "01-sysbench-memory-rnd-read-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_THREADS=2 SYSBENCH_MEMORY_BLOCK_SIZE=1G "
        "SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_TIME=30 "
        "SYSBENCH_MEMORY_OPER=read SYSBENCH_MEMORY_ACCESS_MODE=rnd "
        "run-benchmark sysbench-memory",
        900,
    ),
    (
        "01-sysbench-memory-rnd-write-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_THREADS=2 SYSBENCH_MEMORY_BLOCK_SIZE=1G "
        "SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_TIME=30 "
        "SYSBENCH_MEMORY_OPER=write SYSBENCH_MEMORY_ACCESS_MODE=rnd "
        "run-benchmark sysbench-memory",
        900,
    ),
    *[
        (
            f"02-sysbench-prime-{max_prime}",
            "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
            f"SYSBENCH_THREADS=2 SYSBENCH_TIME=30 SYSBENCH_MAX_PRIME={max_prime} "
            "run-benchmark sysbench-prime",
            180,
        )
        for max_prime in FORMAL_PRIME_MAX_VALUES
    ],
    (
        "03-go-benchmark-formal",
        go_benchmark_command(3),
        1800,
    ),
    (
        "04-php-benchmark-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PHPBENCH_ITERATIONS=2000000 run-benchmark php-benchmark",
        1200,
    ),
    (
        "05-python-benchmark-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PYPERFORMANCE_MODE=rigorous run-benchmark python-benchmark",
        3600,
    ),
    (
        "06-node-octane-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark node-octane",
        1800,
    ),
    (
        "07-java-scimark-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark java-scimark",
        300,
    ),
]


def import_sandbox_class() -> Any:
    try:
        from e2b_code_interpreter import Sandbox
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing SDK dependency: e2b_code_interpreter. "
            "Install it with: pip install e2b-code-interpreter"
        ) from exc
    return Sandbox


def create_sandbox(Sandbox: Any, template_id: str, timeout: int | None) -> Any:
    if timeout is None:
        return Sandbox.create(template=template_id)
    try:
        return Sandbox.create(template=template_id, timeout=timeout)
    except TypeError:
        return Sandbox.create(template=template_id)


def connect_sandbox(Sandbox: Any, sandbox_id: str) -> Any:
    for method_name in ("connect", "from_id", "reconnect"):
        method = getattr(Sandbox, method_name, None)
        if method is None:
            continue
        try:
            return method(sandbox_id=sandbox_id)
        except TypeError:
            try:
                return method(sandbox_id)
            except TypeError:
                continue
    raise RuntimeError("Installed SDK does not expose Sandbox.connect/from_id/reconnect for existing sandboxes.")


def sandbox_id_of(sandbox: Any) -> str:
    for attr in ("sandbox_id", "sandboxId", "id"):
        value = getattr(sandbox, attr, None)
        if value:
            return str(value)
    get_info = getattr(sandbox, "get_info", None)
    if get_info is not None:
        try:
            info = get_info()
            for attr in ("sandbox_id", "sandboxId", "id"):
                value = getattr(info, attr, None)
                if value:
                    return str(value)
            if isinstance(info, dict):
                for key in ("sandbox_id", "sandboxID", "sandboxId", "id"):
                    if info.get(key):
                        return str(info[key])
        except Exception:
            pass
    return ""


def get_info_json(sandbox: Any) -> str:
    get_info = getattr(sandbox, "get_info", None)
    if get_info is None:
        return "{}"
    try:
        info = get_info()
        if isinstance(info, dict):
            return json.dumps(info, ensure_ascii=False, indent=2, default=str)
        return json.dumps(vars(info), ensure_ascii=False, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001 - persist best-effort diagnostic.
        return json.dumps({"error": repr(exc)}, ensure_ascii=False, indent=2)


def kill_sandbox(sandbox: Any) -> str:
    for method_name in ("kill", "close"):
        method = getattr(sandbox, method_name, None)
        if method is None:
            continue
        try:
            result = method()
            return f"{method_name}: {result!r}\n"
        except Exception as exc:  # noqa: BLE001 - keep cleanup diagnostic.
            return f"{method_name} error: {exc!r}\n"
    return "no kill/close method found\n"


def result_field(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def result_exit_code(result: Any) -> int:
    for name in ("exit_code", "exitCode", "returncode", "code"):
        value = result_field(result, name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    error = result_field(result, "error")
    return 1 if error else 0


def sdk_read_file(sandbox: Any, path: str) -> str:
    content = sandbox.files.read(path)
    if isinstance(content, bytes):
        return content.decode("utf-8", "replace")
    return str(content)


def available_cases(suite: str) -> list[Case]:
    return FORMAL_CASES if suite == "formal" else SMOKE_CASES


def selected_cases(names: list[str], suite: str) -> list[Case]:
    cases = available_cases(suite)
    if not names:
        return cases
    selected: list[Case] = []
    wanted = set(names)
    for case in cases:
        suffix = case[0].split("-", 1)[1]
        if case[0] in wanted or suffix in wanted:
            selected.append(case)
    matched = {c[0] for c in selected} | {c[0].split("-", 1)[1] for c in selected}
    missing = wanted - matched
    if missing:
        raise ValueError(f"unknown case(s): {', '.join(sorted(missing))}")
    return selected


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def make_tarball(results_dir: Path) -> Path:
    tar_path = results_dir.with_suffix(".tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(results_dir, arcname=results_dir.name)
    return tar_path


def first_match(pattern: str, text: str, group: int | str = 1) -> str:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    return str(match.group(group))


def parse_memory(case: str, stdout: str) -> dict[str, str]:
    mode = ""
    if "seq-read" in case:
        mode = "seq-read"
    elif "seq-write" in case:
        mode = "seq-write"
    elif "rnd-read" in case:
        mode = "rnd-read"
    elif "rnd-write" in case:
        mode = "rnd-write"
    return {
        "mode": mode or case,
        "transferred_mib": first_match(r"([0-9.]+)\s+MiB transferred", stdout),
        "throughput_mib_s": first_match(r"\(([0-9.]+)\s+MiB/sec\)", stdout),
        "events": first_match(r"total number of events:\s*([0-9]+)", stdout),
        "total_time_s": first_match(r"total time:\s*([0-9.]+)s", stdout),
        "avg_latency_ms": first_match(r"avg:\s*([0-9.]+)", stdout),
        "p95_latency_ms": first_match(r"95th percentile:\s*([0-9.]+)", stdout),
    }


def parse_prime(case: str, stdout: str) -> dict[str, str]:
    return {
        "max_prime": first_match(r"sysbench-prime-([0-9]+)", case) or first_match(r"max[-_ ]prime[=:\s]+([0-9]+)", stdout),
        "events_per_sec": first_match(r"events per second:\s*([0-9.]+)", stdout),
        "total_events": first_match(r"total number of events:\s*([0-9]+)", stdout),
        "total_time_s": first_match(r"total time:\s*([0-9.]+)s", stdout),
    }


def parse_go(stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for name in ("http", "json", "build", "garbage"):
        patterns = [
            rf'"?{name}"?.*?"average[_-]?ns[_-]?per[_-]?op"?\s*[:=]\s*([0-9.]+)',
            rf"{name}.*?average.*?([0-9.]+)\s*ns/op",
            rf"{name}.*?([0-9.]+)\s*ns/op.*?average",
        ]
        for pattern in patterns:
            value = first_match(pattern, stdout)
            if value:
                rows.append({"case": name, "average_ns_op": value})
                seen.add(name)
                break
    if not rows:
        for match in re.finditer(r"(http|json|build|garbage).*?([0-9.]+)\s*ns/op", stdout, re.IGNORECASE):
            name = match.group(1).lower()
            if name in seen:
                continue
            rows.append({"case": name, "average_ns_op": match.group(2)})
            seen.add(name)
    return rows


def parse_runtime(case: str, stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if "go-benchmark" in case:
        for item in parse_go(stdout):
            rows.append({"benchmark": "go-benchmark", "metric": item["case"], "value": item["average_ns_op"], "unit": "ns/op"})
    elif "php-benchmark" in case:
        score = first_match(r"(?:score|total score)[^0-9]*([0-9.]+)", stdout)
        if score:
            rows.append({"benchmark": "php-benchmark", "metric": "score", "value": score, "unit": "score"})
        total = first_match(r"(?:total[_ ]time|time)[^0-9]*([0-9.]+)\s*s", stdout)
        if total:
            rows.append({"benchmark": "php-benchmark", "metric": "total_time", "value": total, "unit": "s"})
    elif "python-benchmark" in case:
        for match in re.finditer(r"^([A-Za-z0-9_]+):\s*(?:Mean \+- std dev:\s*)?([0-9.]+)\s*([mun]?s|sec|ms)", stdout, re.MULTILINE):
            rows.append({"benchmark": "python-benchmark", "metric": match.group(1), "value": match.group(2), "unit": match.group(3)})
    elif "node-octane" in case:
        score = first_match(r"(?:Octane Score|Score):\s*([0-9.]+)", stdout)
        if score:
            rows.append({"benchmark": "node-octane", "metric": "score", "value": score, "unit": "score"})
    elif "java-scimark" in case:
        for metric in ("Composite", "FFT", "SOR", "Monte Carlo", "Sparse matmult", "LU"):
            value = first_match(rf"{re.escape(metric)}(?:\s+Score)?:\s*([0-9.]+)", stdout)
            if value:
                rows.append({"benchmark": "java-scimark", "metric": metric, "value": value, "unit": "score"})
    return rows


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No parsed rows._\n"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(out) + "\n"


def load_summary_stdout(results_dir: Path, item: dict[str, Any]) -> str:
    result_dir = Path(item.get("result_dir") or results_dir)
    log_path = result_dir / f"{item['case']}.log"
    if log_path.exists():
        return log_path.read_text(encoding="utf-8", errors="replace")
    stdout_path = result_dir / f"{item['case']}.stdout.log"
    if stdout_path.exists():
        return stdout_path.read_text(encoding="utf-8", errors="replace")
    return ""


def generate_report(results_dir: Path, summary: list[dict[str, Any]]) -> Path:
    memory_rows: list[list[str]] = []
    prime_rows: list[list[str]] = []
    runtime_rows: list[list[str]] = []
    status_rows: list[list[str]] = []

    for item in summary:
        case = str(item["case"])
        stdout = load_summary_stdout(results_dir, item)
        status_rows.append(
            [
                case,
                str(item.get("sandbox_id", "")),
                str(item.get("exit_code", "")),
                str(item.get("elapsed_sec", "")),
                str(item.get("result_dir", "")),
            ]
        )
        if "sysbench-memory" in case:
            parsed = parse_memory(case, stdout)
            memory_rows.append(
                [
                    parsed["mode"],
                    parsed["transferred_mib"],
                    parsed["throughput_mib_s"],
                    parsed["events"],
                    parsed["total_time_s"],
                    parsed["avg_latency_ms"],
                    parsed["p95_latency_ms"],
                ]
            )
        elif "sysbench-prime" in case:
            parsed = parse_prime(case, stdout)
            prime_rows.append(
                [
                    parsed["max_prime"],
                    parsed["events_per_sec"],
                    parsed["total_events"],
                    parsed["total_time_s"],
                ]
            )
        else:
            for parsed in parse_runtime(case, stdout):
                runtime_rows.append([parsed["benchmark"], parsed["metric"], parsed["value"], parsed["unit"]])

    passed = sum(1 for item in summary if int(item.get("exit_code", 255)) == 0)
    failed = len(summary) - passed
    text = [
        "# CubeSandbox SDK Benchmark Report",
        "",
        f"- Results dir: `{results_dir}`",
        f"- Generated at: `{time.strftime('%Y-%m-%dT%H:%M:%S%z')}`",
        f"- Cases: `{len(summary)}` total, `{passed}` passed, `{failed}` failed",
        "",
        "## Execution Status",
        "",
        markdown_table(["case", "sandbox_id", "exit_code", "elapsed_sec", "result_dir"], status_rows),
        "",
        "## Sysbench Memory",
        "",
        markdown_table(
            ["mode", "transferred_mib", "throughput_mib_s", "events", "total_time_s", "avg_latency_ms", "p95_latency_ms"],
            memory_rows,
        ),
        "",
        "## Sysbench Prime",
        "",
        markdown_table(["max_prime", "events_per_sec", "total_events", "total_time_s"], prime_rows),
        "",
        "## Runtime Benchmarks",
        "",
        markdown_table(["benchmark", "metric", "value", "unit"], runtime_rows),
        "",
        "## Raw Artifacts",
        "",
        "Each case saves `.cmd`, `.log`, `.stdout.log`, `.stderr.log`, `.result.json`, and Sandbox `sandbox.json` where available.",
        "",
    ]
    report_path = results_dir / "benchmark-report.md"
    write_text(report_path, "\n".join(text))
    return report_path


def rewrite_case_command(raw_cmd: str, sandbox_out_dir: str) -> str:
    bench_out_dir = f"{sandbox_out_dir.rstrip('/')}/results"
    return raw_cmd.replace("CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results", f"CUBE_BENCH_OUT_DIR={bench_out_dir}")


def run_sdk_case(sandbox: Any, case: Case, result_dir: Path, cwd: str, sandbox_out_dir: str) -> dict[str, Any]:
    name, raw_cmd, timeout = case
    effective_cmd = rewrite_case_command(raw_cmd, sandbox_out_dir)
    sandbox_log = f"{sandbox_out_dir.rstrip('/')}/{name}.log"
    wrapped = (
        "set -o pipefail; "
        f"mkdir -p {shlex.quote(sandbox_out_dir)} {shlex.quote(cwd)} {shlex.quote(sandbox_out_dir.rstrip('/') + '/results')}; "
        f"cd {shlex.quote(cwd)}; "
        f"{effective_cmd} 2>&1 | tee {shlex.quote(sandbox_log)}"
    )
    sdk_cmd = f"/bin/bash -lc {shlex.quote(wrapped)}"
    sandbox_id = sandbox_id_of(sandbox)
    start = time.time()
    print(f"START {name} sandbox={sandbox_id or '<unknown>'} timeout={timeout}s", flush=True)

    result: Any = None
    error = None
    warning = None
    copy_method = "files.read"
    try:
        result = sandbox.commands.run(sdk_cmd, timeout=timeout)
        exit_code = result_exit_code(result)
        stdout = result_field(result, "stdout", "") or ""
        stderr = result_field(result, "stderr", "") or ""
    except Exception as exc:  # noqa: BLE001 - persist SDK/proxy failures.
        exit_code = 255
        stdout = ""
        stderr = repr(exc) + "\n"
        error = repr(exc)

    try:
        full_log = sdk_read_file(sandbox, sandbox_log)
    except Exception as exc:  # noqa: BLE001 - fall back to streamed stdout.
        full_log = stdout
        copy_method = "sdk_stdout_fallback"
        read_error = f"files.read({sandbox_log}) failed: {exc!r}"
        if stdout and error is None:
            warning = read_error
        else:
            error = (error + "; " if error else "") + read_error

    elapsed = time.time() - start
    write_text(result_dir / f"{name}.cmd", effective_cmd + "\n")
    if effective_cmd != raw_cmd:
        write_text(result_dir / f"{name}.original_cmd", raw_cmd + "\n")
    write_text(result_dir / f"{name}.sdk_cmd", sdk_cmd + "\n")
    write_text(result_dir / f"{name}.log", full_log)
    write_text(result_dir / f"{name}.stdout.log", stdout)
    write_text(result_dir / f"{name}.stderr.log", stderr)
    write_text(
        result_dir / f"{name}.result.json",
        json.dumps(
            {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "error": error,
                "warning": warning,
                "copy_method": copy_method,
                "result_repr": repr(result),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )

    item = {
        "case": name,
        "sandbox_id": sandbox_id,
        "exit_code": exit_code,
        "elapsed_sec": round(elapsed, 3),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
        "log_bytes": len(full_log.encode("utf-8")),
        "sandbox_log": sandbox_log,
        "sandbox_work_dir": cwd,
        "sandbox_out_dir": sandbox_out_dir,
        "result_dir": str(result_dir),
        "copy_method": copy_method,
        "warning": warning,
        "error": error,
    }
    print(
        f"END {name} exit_code={exit_code} elapsed={elapsed:.1f}s "
        f"log={item['log_bytes']} stdout={item['stdout_bytes']} stderr={item['stderr_bytes']}",
        flush=True,
    )
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default=os.environ.get("E2B_API_URL"), help="Cube E2B-compatible API URL.")
    parser.add_argument("--api-key", default=os.environ.get("E2B_API_KEY", "e2b_000000"))
    parser.add_argument("--ssl-cert-file", default=os.environ.get("CUBE_SSL_CERT_FILE") or os.environ.get("SSL_CERT_FILE"))
    parser.add_argument("--template-id", default=os.environ.get("CUBE_TEMPLATE_ID"), help="Template ID used to create Sandbox instances.")
    parser.add_argument("--sandbox-id", help="Existing Sandbox ID. Requires an SDK version that supports connect/from_id/reconnect.")
    parser.add_argument("--sandbox-timeout", type=int, default=None, help="Optional SDK Sandbox.create timeout/lifetime value.")
    parser.add_argument("--results-dir", default=f"cube-bench-sdk-results-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--suite", choices=("smoke", "formal"), default="formal")
    parser.add_argument("--case", action="append", default=[], help="Case name to run; repeatable.")
    parser.add_argument("--cwd", help="Sandbox working directory. Defaults to <sandbox-out-dir>/work.")
    parser.add_argument("--sandbox-out-dir", default="/tmp/cube-bench-sdk")
    parser.add_argument("--delete", action="store_true", help="Kill/close Sandbox after the run.")
    parser.add_argument("--no-tar", action="store_true", help="Do not create a .tar.gz result archive.")
    parser.add_argument("--no-report", action="store_true", help="Do not generate benchmark-report.md.")
    parser.add_argument("--list-cases", action="store_true", help="Print available cases and exit.")
    isolate = parser.add_mutually_exclusive_group()
    isolate.add_argument(
        "--isolate-cases",
        dest="isolate_cases",
        action="store_true",
        default=None,
        help="Create a fresh Sandbox per case. Default for formal runs created from Template.",
    )
    isolate.add_argument(
        "--single-sandbox",
        dest="isolate_cases",
        action="store_false",
        help="Run all cases in one Sandbox.",
    )
    args = parser.parse_args()

    cases = selected_cases(args.case, args.suite)
    if args.list_cases:
        for name, cmd, timeout in cases:
            print(f"{name}\ttimeout={timeout}\t{cmd}")
        return 0

    if not args.api_url:
        parser.error("--api-url or E2B_API_URL is required")
    if not args.sandbox_id and not args.template_id:
        parser.error("either --sandbox-id or --template-id/CUBE_TEMPLATE_ID is required")
    if args.isolate_cases is None:
        args.isolate_cases = args.suite == "formal" and bool(args.template_id) and not args.sandbox_id
    if args.sandbox_id and args.isolate_cases:
        parser.error("--isolate-cases requires --template-id without --sandbox-id")
    if not args.cwd:
        args.cwd = f"{args.sandbox_out_dir.rstrip('/')}/work"

    os.environ["E2B_API_URL"] = args.api_url
    os.environ["E2B_API_KEY"] = args.api_key
    if args.ssl_cert_file:
        os.environ["SSL_CERT_FILE"] = args.ssl_cert_file

    Sandbox = import_sandbox_class()
    results = Path(args.results_dir).resolve()
    results.mkdir(parents=True, exist_ok=True)
    write_text(
        results / "run-context.json",
        json.dumps(
            {
                "api_url": args.api_url,
                "template_id": args.template_id,
                "sandbox_id": args.sandbox_id,
                "suite": args.suite,
                "cases": [case[0] for case in cases],
                "isolate_cases": args.isolate_cases,
                "cwd": args.cwd,
                "sandbox_out_dir": args.sandbox_out_dir,
                "ssl_cert_file": args.ssl_cert_file,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    summary: list[dict[str, Any]] = []
    try:
        if args.isolate_cases:
            for case in cases:
                sandbox = create_sandbox(Sandbox, args.template_id, args.sandbox_timeout)
                case_dir = results / case[0]
                write_text(case_dir / "sandbox.json", get_info_json(sandbox))
                summary.append(run_sdk_case(sandbox, case, case_dir, args.cwd, args.sandbox_out_dir))
                if args.delete:
                    write_text(case_dir / "delete-sandbox.txt", kill_sandbox(sandbox))
        else:
            sandbox = connect_sandbox(Sandbox, args.sandbox_id) if args.sandbox_id else create_sandbox(Sandbox, args.template_id, args.sandbox_timeout)
            write_text(results / "sandbox.json", get_info_json(sandbox))
            for case in cases:
                summary.append(run_sdk_case(sandbox, case, results, args.cwd, args.sandbox_out_dir))
            if args.delete:
                write_text(results / "delete-sandbox.txt", kill_sandbox(sandbox))
    finally:
        write_text(results / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.no_report:
        report_path = generate_report(results, summary)
        print(f"REPORT {report_path}", flush=True)
    if not args.no_tar:
        tar_path = make_tarball(results)
        print(f"TAR {tar_path}", flush=True)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(int(item.get("exit_code", 255)) != 0 for item in summary) else 0


if __name__ == "__main__":
    sys.exit(main())
