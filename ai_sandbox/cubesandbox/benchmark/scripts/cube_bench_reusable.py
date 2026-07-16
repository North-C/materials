#!/usr/bin/env python3
"""Reusable CubeSandbox benchmark runner.

Copy this file to any CubeSandbox environment that can reach CubeAPI and the
Sandbox envd port. It uses only Python standard-library modules.

Typical formal run:

    python3 cube_bench_reusable.py --template-id tpl-xxx --suite formal --delete

Typical existing Sandbox run:

    python3 cube_bench_reusable.py --sandbox-id sbox-xxx --sandbox-ip 10.0.0.10
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import ssl
import struct
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


Case = tuple[str, str, int]

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
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "GO_BENCH_REPEATS=1 run-benchmark go-benchmark",
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
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "GO_BENCH_REPEATS=3 run-benchmark go-benchmark",
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


def ssl_context(insecure: bool) -> ssl.SSLContext | None:
    if not insecure:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001 - explicit CLI opt-in.


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 180,
    context: ssl.SSLContext | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        raw = resp.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def create_sandbox(cube_api: str, template_id: str, timeout: int, context: ssl.SSLContext | None) -> str:
    payload = {
        "templateID": template_id,
        "timeout": timeout,
        "metadata": {"verification": "cube-bench-reusable"},
    }
    data = http_json("POST", f"{cube_api.rstrip('/')}/sandboxes", payload, timeout=240, context=context)
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected create sandbox response: {data!r}")
    sandbox_id = data.get("sandboxID") or data.get("sandboxId") or data.get("id")
    if not sandbox_id:
        raise RuntimeError(f"create sandbox response missing sandbox ID: {data!r}")
    return str(sandbox_id)


def get_sandbox_info(cube_api: str, sandbox_id: str, context: ssl.SSLContext | None) -> dict[str, Any]:
    data = http_json("GET", f"{cube_api.rstrip('/')}/sandboxes/{sandbox_id}", None, timeout=60, context=context)
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected sandbox info response: {data!r}")
    return data


def delete_sandbox(cube_api: str, sandbox_id: str, context: ssl.SSLContext | None) -> tuple[int, str]:
    req = urllib.request.Request(f"{cube_api.rstrip('/')}/sandboxes/{sandbox_id}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def get_sandbox_ip(sandbox_id: str) -> str:
    proc = subprocess.run(
        ["cubemastercli", "cubebox", "info", "--sandboxid", sandbox_id],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("SANDBOX_IP"):
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    raise RuntimeError(f"could not find SANDBOX_IP in cubemastercli output:\n{proc.stdout}")


def check_url(url: str, timeout: int = 5, context: ssl.SSLContext | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.status, resp.read()


def encode_connect(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return bytes([0]) + struct.pack(">I", len(raw)) + raw


def parse_exit_status(status: Any) -> int | None:
    if isinstance(status, str):
        match = re.search(r"exit status\s+(-?\d+)", status)
        if match:
            return int(match.group(1))
    return None


def run_envd_command(envd_url: str, cmd: str, timeout: int, cwd: str) -> tuple[bytes, list[Any], str, str, int]:
    payload = {
        "process": {
            "cmd": "/bin/bash",
            "args": ["-l", "-c", cmd],
            "envs": {},
            "cwd": cwd,
        },
        "stdin": False,
    }
    req = urllib.request.Request(
        envd_url,
        data=encode_connect(payload),
        method="POST",
        headers={
            "Content-Type": "application/connect+json",
            "Connect-Protocol-Version": "1",
            "Connect-Content-Encoding": "identity",
            "Connect-Timeout-Ms": str(timeout * 1000),
            "Authorization": "Basic cm9vdDo=",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout + 15) as resp:
        raw = resp.read()

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    exit_code = 0
    events: list[Any] = []
    idx = 0
    while idx + 5 <= len(raw):
        flags = raw[idx]
        length = struct.unpack(">I", raw[idx + 1 : idx + 5])[0]
        idx += 5
        frame = raw[idx : idx + length]
        idx += length
        try:
            value = json.loads(frame or b"{}")
        except Exception as exc:  # noqa: BLE001 - preserve malformed frame detail.
            events.append(
                {
                    "flags": flags,
                    "decode_error": str(exc),
                    "raw": frame.decode("utf-8", "replace"),
                }
            )
            continue
        events.append({"flags": flags, "json": value})
        if flags & 2:
            continue
        event = value.get("event") or {}
        data = event.get("data") or {}
        if "stdout" in data:
            stdout_parts.append(base64.b64decode(data["stdout"]).decode("utf-8", "replace"))
        if "stderr" in data:
            stderr_parts.append(base64.b64decode(data["stderr"]).decode("utf-8", "replace"))
        end = event.get("end")
        if end:
            parsed = end.get("exitCode")
            if parsed is None:
                parsed = parse_exit_status(end.get("status"))
            exit_code = int(parsed or 0)
    return raw, events, "".join(stdout_parts), "".join(stderr_parts), exit_code


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
    transferred = first_match(r"([0-9.]+)\s+MiB transferred", stdout)
    throughput = first_match(r"\(([0-9.]+)\s+MiB/sec\)", stdout)
    events = first_match(r"total number of events:\s*([0-9]+)", stdout)
    total_time = first_match(r"total time:\s*([0-9.]+)s", stdout)
    avg = first_match(r"avg:\s*([0-9.]+)", stdout)
    p95 = first_match(r"95th percentile:\s*([0-9.]+)", stdout)
    return {
        "mode": mode or case,
        "transferred_mib": transferred,
        "throughput_mib_s": throughput,
        "events": events,
        "total_time_s": total_time,
        "avg_latency_ms": avg,
        "p95_latency_ms": p95,
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
        rows.append(
            {
                "benchmark": "php-benchmark",
                "metric": "score",
                "value": first_match(r"(?:score|total score)[^0-9]*([0-9.]+)", stdout),
                "unit": "score",
            }
        )
        total = first_match(r"(?:total[_ ]time|time)[^0-9]*([0-9.]+)\s*s", stdout)
        if total:
            rows.append({"benchmark": "php-benchmark", "metric": "total_time", "value": total, "unit": "s"})
    elif "python-benchmark" in case:
        for match in re.finditer(r"^([A-Za-z0-9_]+):\s*(?:Mean \+- std dev:\s*)?([0-9.]+)\s*([mun]?s|sec|ms)", stdout, re.MULTILINE):
            rows.append({"benchmark": "python-benchmark", "metric": match.group(1), "value": match.group(2), "unit": match.group(3)})
    elif "node-octane" in case:
        rows.append(
            {
                "benchmark": "node-octane",
                "metric": "score",
                "value": first_match(r"(?:Octane Score|Score):\s*([0-9.]+)", stdout),
                "unit": "score",
            }
        )
    elif "java-scimark" in case:
        for metric in ("Composite", "FFT", "SOR", "Monte Carlo", "Sparse matmult", "LU"):
            value = first_match(rf"{re.escape(metric)}(?:\s+Score)?:\s*([0-9.]+)", stdout)
            if value:
                rows.append({"benchmark": "java-scimark", "metric": metric, "value": value, "unit": "score"})
    return [row for row in rows if row.get("value")]


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
    stdout_path = result_dir / f"{item['case']}.stdout"
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
                str(item.get("rc", "")),
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

    passed = sum(1 for item in summary if int(item.get("rc", 255)) == 0)
    failed = len(summary) - passed
    text = [
        "# CubeSandbox Benchmark Report",
        "",
        f"- Results dir: `{results_dir}`",
        f"- Generated at: `{time.strftime('%Y-%m-%dT%H:%M:%S%z')}`",
        f"- Cases: `{len(summary)}` total, `{passed}` passed, `{failed}` failed",
        "",
        "## Execution Status",
        "",
        markdown_table(["case", "sandbox_id", "rc", "elapsed_sec", "result_dir"], status_rows),
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
        "Each case saves `.cmd`, `.stdout`, `.stderr`, `.rc`, `.events.json`, and `.raw` files. "
        "Use `.stdout` for benchmark output and `.events.json` for envd Connect frames.",
        "",
    ]
    report_path = results_dir / "benchmark-report.md"
    write_text(report_path, "\n".join(text))
    return report_path


def save_health(result_dir: Path, sandbox_ip: str) -> None:
    lines: list[str] = []
    for name, url in (
        ("envd_49983", f"http://{sandbox_ip}:49983/health"),
        ("bench_49999", f"http://{sandbox_ip}:49999/health"),
    ):
        try:
            status, body = check_url(url)
            lines.append(f"{name}={status}")
            if body:
                lines.append(f"{name}_body={body.decode('utf-8', 'replace')}")
        except Exception as exc:  # noqa: BLE001 - health failures should be persisted.
            lines.append(f"{name}_error={exc!r}")
    write_text(result_dir / "health.txt", "\n".join(lines) + "\n")


def run_case(
    case: Case,
    result_dir: Path,
    sandbox_id: str,
    sandbox_ip: str,
    cwd: str,
) -> dict[str, Any]:
    name, cmd, timeout = case
    envd_url = f"http://{sandbox_ip}:49983/process.Process/Start"
    start = time.time()
    print(f"START {name} sandbox={sandbox_id} timeout={timeout}s", flush=True)
    try:
        raw, events, stdout, stderr, rc = run_envd_command(envd_url, cmd, timeout, cwd)
        error = None
    except Exception as exc:  # noqa: BLE001 - keep runner alive and persist error.
        raw, events, stdout, stderr, rc = b"", [], "", repr(exc) + "\n", 255
        error = repr(exc)
    elapsed = time.time() - start

    write_text(result_dir / f"{name}.cmd", cmd + "\n")
    write_text(result_dir / f"{name}.stdout", stdout)
    write_text(result_dir / f"{name}.stderr", stderr)
    write_text(result_dir / f"{name}.rc", f"{rc}\n")
    write_text(result_dir / f"{name}.events.json", json.dumps(events, ensure_ascii=False, indent=2))
    (result_dir / f"{name}.raw").write_bytes(raw)

    item = {
        "case": name,
        "sandbox_id": sandbox_id,
        "sandbox_ip": sandbox_ip,
        "rc": rc,
        "elapsed_sec": round(elapsed, 3),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
        "result_dir": str(result_dir),
        "error": error,
    }
    print(
        f"END {name} rc={rc} elapsed={elapsed:.1f}s "
        f"stdout={item['stdout_bytes']} stderr={item['stderr_bytes']}",
        flush=True,
    )
    return item


def resolve_sandbox_ip(sandbox_id: str, sandbox_ip: str | None) -> str:
    if sandbox_ip:
        return sandbox_ip
    return get_sandbox_ip(sandbox_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cube-api", default=os.environ.get("CUBE_API", "http://127.0.0.1:3000"))
    parser.add_argument("--template-id", help="Template ID used to create Sandbox instances.")
    parser.add_argument("--sandbox-id", help="Existing Sandbox ID. If omitted, --template-id is required.")
    parser.add_argument("--sandbox-ip", help="Sandbox IP. Required when cubemastercli is unavailable.")
    parser.add_argument("--sandbox-timeout", type=int, default=7200)
    parser.add_argument("--results-dir", default=f"cube-bench-results-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--suite", choices=("smoke", "formal"), default="formal")
    parser.add_argument("--case", action="append", default=[], help="Case name to run; repeatable.")
    parser.add_argument("--cwd", default="/opt/cube-bench")
    parser.add_argument("--delete", action="store_true", help="Delete Sandboxes created or used by this run after execution.")
    parser.add_argument("--no-tar", action="store_true", help="Do not create a .tar.gz result archive.")
    parser.add_argument("--no-report", action="store_true", help="Do not generate benchmark-report.md.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification for HTTPS CubeAPI.")
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

    if args.isolate_cases is None:
        args.isolate_cases = args.suite == "formal" and bool(args.template_id) and not args.sandbox_id
    if not args.sandbox_id and not args.template_id:
        parser.error("either --sandbox-id or --template-id is required")
    if args.sandbox_id and args.isolate_cases:
        parser.error("--isolate-cases requires --template-id without --sandbox-id")
    has_cubemastercli = shutil.which("cubemastercli") is not None
    if args.isolate_cases and not has_cubemastercli:
        parser.error("--isolate-cases requires cubemastercli to resolve each newly created Sandbox IP")
    if not args.isolate_cases and not has_cubemastercli and not args.sandbox_ip:
        parser.error("cubemastercli is required unless --sandbox-ip is provided")

    context = ssl_context(args.insecure)
    results = Path(args.results_dir).resolve()
    results.mkdir(parents=True, exist_ok=True)
    write_text(
        results / "run-context.json",
        json.dumps(
            {
                "cube_api": args.cube_api,
                "template_id": args.template_id,
                "sandbox_id": args.sandbox_id,
                "sandbox_ip": args.sandbox_ip,
                "suite": args.suite,
                "cases": [case[0] for case in cases],
                "isolate_cases": args.isolate_cases,
                "cwd": args.cwd,
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
                sandbox_id = create_sandbox(args.cube_api, args.template_id, args.sandbox_timeout, context)
                sandbox_ip = resolve_sandbox_ip(sandbox_id, None)
                case_dir = results / case[0]
                write_text(
                    case_dir / "sandbox.json",
                    json.dumps(
                        get_sandbox_info(args.cube_api, sandbox_id, context),
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
                save_health(case_dir, sandbox_ip)
                summary.append(run_case(case, case_dir, sandbox_id, sandbox_ip, args.cwd))
                if args.delete:
                    code, body = delete_sandbox(args.cube_api, sandbox_id, context)
                    write_text(case_dir / "delete-sandbox.txt", f"http_code={code}\n{body}")
        else:
            sandbox_id = args.sandbox_id
            if not sandbox_id:
                sandbox_id = create_sandbox(args.cube_api, args.template_id, args.sandbox_timeout, context)
            sandbox_ip = resolve_sandbox_ip(sandbox_id, args.sandbox_ip)
            write_text(
                results / "sandbox.json",
                json.dumps(get_sandbox_info(args.cube_api, sandbox_id, context), ensure_ascii=False, indent=2),
            )
            save_health(results, sandbox_ip)
            for case in cases:
                summary.append(run_case(case, results, sandbox_id, sandbox_ip, args.cwd))
            if args.delete:
                code, body = delete_sandbox(args.cube_api, sandbox_id, context)
                write_text(results / "delete-sandbox.txt", f"http_code={code}\n{body}")
    finally:
        write_text(results / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.no_report:
        report_path = generate_report(results, summary)
        print(f"REPORT {report_path}", flush=True)
    if not args.no_tar:
        tar_path = make_tarball(results)
        print(f"TAR {tar_path}", flush=True)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(int(item.get("rc", 255)) != 0 for item in summary) else 0


if __name__ == "__main__":
    sys.exit(main())
