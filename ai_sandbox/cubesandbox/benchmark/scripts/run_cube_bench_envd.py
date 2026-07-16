#!/usr/bin/env python3
"""Run cube-bench-suite benchmarks through CubeSandbox envd.

This script is intended to run on a CubeSandbox master/worker host where:

* CubeAPI is reachable, usually at http://127.0.0.1:3000.
* cubemastercli is in PATH, so the script can resolve Sandbox IPs.
* The Template was created from cube-bench-suite and exposes:
  * 49983: envd Process API
  * 49999: benchmark health server

It uses only Python standard-library modules.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CASES: list[tuple[str, str, int]] = [
    ("00-versions", "run-benchmark versions", 60),
    (
        "01-sysbench-memory-all",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_MEMORY_TIME=5 SYSBENCH_MEMORY_TOTAL_SIZE=10G "
        "SYSBENCH_MEMORY_BLOCK_SIZE=1K SYSBENCH_MEMORY_THREADS=8 "
        "run-benchmark sysbench-memory-all",
        90,
    ),
    (
        "02-sysbench-prime",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "SYSBENCH_TIME=5 SYSBENCH_MAX_PRIME=5000 SYSBENCH_THREADS=8 "
        "run-benchmark sysbench-prime",
        90,
    ),
    (
        "03-go-benchmark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "GO_BENCH_CASES=build,http,json,garbage GO_BENCH_DISABLE_PERF=1 "
        "GO_BENCH_REPEATS=1 run-benchmark go-benchmark",
        360,
    ),
    (
        "04-php-benchmark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PHPBENCH_ITERATIONS=100000 run-benchmark php-benchmark",
        180,
    ),
    (
        "05-python-benchmark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "PYPERFORMANCE_BENCHMARKS=python_startup,json_dumps "
        "PYPERFORMANCE_MODE=fast run-benchmark python-benchmark",
        420,
    ),
    (
        "06-node-octane",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark node-octane",
        720,
    ),
    (
        "07-java-scimark",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results run-benchmark java-scimark",
        180,
    ),
]

FORMAL_PRIME_MAX_VALUES = [1000, 2000, 3000, 5000, 10000, 20000, 30000, 50000, 100000]

FORMAL_CASES: list[tuple[str, str, int]] = [
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
            120,
        )
        for max_prime in FORMAL_PRIME_MAX_VALUES
    ],
    (
        "03-go-benchmark-formal",
        "CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results "
        "GO_BENCH_CASES=build,http,json,garbage GO_BENCH_DISABLE_PERF=1 "
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


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 180) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def create_sandbox(cube_api: str, template_id: str, timeout: int) -> str:
    payload = {
        "templateID": template_id,
        "timeout": timeout,
        "metadata": {"verification": "cube-bench-envd-reuse"},
    }
    data = http_json("POST", f"{cube_api.rstrip('/')}/sandboxes", payload, timeout=240)
    sandbox_id = data.get("sandboxID") if isinstance(data, dict) else None
    if not sandbox_id:
        raise RuntimeError(f"create sandbox response missing sandboxID: {data!r}")
    return sandbox_id


def get_sandbox_info(cube_api: str, sandbox_id: str) -> dict[str, Any]:
    data = http_json("GET", f"{cube_api.rstrip('/')}/sandboxes/{sandbox_id}", None, timeout=60)
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected sandbox info response: {data!r}")
    return data


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


def check_url(url: str, timeout: int = 5) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        except Exception as exc:  # noqa: BLE001 - preserve malformed frame detail
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


def selected_cases(names: list[str], suite: str) -> list[tuple[str, str, int]]:
    cases = FORMAL_CASES if suite == "formal" else DEFAULT_CASES
    if not names:
        return cases
    selected = []
    wanted = set(names)
    for case in cases:
        if case[0] in wanted or case[0].split("-", 1)[1] in wanted:
            selected.append(case)
    missing = wanted - {c[0] for c in selected} - {c[0].split("-", 1)[1] for c in selected}
    if missing:
        raise ValueError(f"unknown case(s): {', '.join(sorted(missing))}")
    return selected


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", errors="replace")


def make_tarball(results_dir: Path) -> Path:
    tar_path = results_dir.with_suffix(".tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(results_dir, arcname=results_dir.name)
    return tar_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cube-api", default=os.environ.get("CUBE_API", "http://127.0.0.1:3000"))
    parser.add_argument("--template-id", help="Template ID to create a sandbox from.")
    parser.add_argument("--sandbox-id", help="Existing sandbox ID. If omitted, --template-id is required.")
    parser.add_argument("--sandbox-ip", help="Existing sandbox IP. If omitted, resolved with cubemastercli.")
    parser.add_argument("--sandbox-timeout", type=int, default=3600)
    parser.add_argument("--results-dir", default=f"cube-bench-results-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--suite", choices=("smoke", "formal"), default="smoke", help="Benchmark suite to run when --case is not specified.")
    parser.add_argument("--case", action="append", default=[], help="Case name to run; repeatable.")
    parser.add_argument("--cwd", default="/opt/cube-bench")
    parser.add_argument("--delete", action="store_true", help="Delete sandbox after the run.")
    parser.add_argument("--no-tar", action="store_true", help="Do not create a .tar.gz result archive.")
    args = parser.parse_args()

    if not args.sandbox_id and not args.template_id:
        parser.error("either --sandbox-id or --template-id is required")
    if shutil.which("cubemastercli") is None and not args.sandbox_ip:
        parser.error("cubemastercli is required unless --sandbox-ip is provided")

    results = Path(args.results_dir).resolve()
    results.mkdir(parents=True, exist_ok=True)

    sandbox_id = args.sandbox_id
    created = False
    if not sandbox_id:
        sandbox_id = create_sandbox(args.cube_api, args.template_id, args.sandbox_timeout)
        created = True

    sandbox_info = get_sandbox_info(args.cube_api, sandbox_id)
    sandbox_ip = args.sandbox_ip or get_sandbox_ip(sandbox_id)
    envd_url = f"http://{sandbox_ip}:49983/process.Process/Start"

    context = {
        "cube_api": args.cube_api,
        "template_id": args.template_id or sandbox_info.get("templateID"),
        "sandbox_id": sandbox_id,
        "sandbox_ip": sandbox_ip,
        "sandbox_info": sandbox_info,
        "envd_url": envd_url,
        "suite": args.suite,
        "created_by_script": created,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_text(results / "context.json", json.dumps(context, ensure_ascii=False, indent=2))

    health_status, _ = check_url(f"http://{sandbox_ip}:49983/health")
    bench_status, bench_body = check_url(f"http://{sandbox_ip}:49999/health")
    write_text(
        results / "health.txt",
        f"envd_49983={health_status}\nbench_49999={bench_status}\n"
        f"bench_body={bench_body.decode('utf-8', 'replace')}\n",
    )

    summary: list[dict[str, Any]] = []
    for name, cmd, timeout in selected_cases(args.case, args.suite):
        start = time.time()
        print(f"START {name} timeout={timeout}s", flush=True)
        try:
            raw, events, stdout, stderr, rc = run_envd_command(envd_url, cmd, timeout, args.cwd)
            error = None
        except Exception as exc:  # noqa: BLE001 - keep test runner alive and save error
            raw, events, stdout, stderr, rc = b"", [], "", repr(exc) + "\n", 255
            error = repr(exc)
        elapsed = time.time() - start
        write_text(results / f"{name}.cmd", cmd + "\n")
        write_text(results / f"{name}.stdout", stdout)
        write_text(results / f"{name}.stderr", stderr)
        write_text(results / f"{name}.rc", f"{rc}\n")
        write_text(results / f"{name}.events.json", json.dumps(events, ensure_ascii=False, indent=2))
        (results / f"{name}.raw").write_bytes(raw)
        item = {
            "case": name,
            "rc": rc,
            "elapsed_sec": round(elapsed, 3),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "error": error,
        }
        summary.append(item)
        print(
            f"END {name} rc={rc} elapsed={elapsed:.1f}s "
            f"stdout={item['stdout_bytes']} stderr={item['stderr_bytes']}",
            flush=True,
        )

    write_text(results / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.no_tar:
        tar_path = make_tarball(results)
        print(f"TAR {tar_path}", flush=True)

    if args.delete:
        try:
            req = urllib.request.Request(
                f"{args.cube_api.rstrip('/')}/sandboxes/{sandbox_id}",
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                write_text(results / "delete-sandbox.http_code", f"{resp.status}\n")
        except urllib.error.HTTPError as exc:
            write_text(results / "delete-sandbox.http_code", f"{exc.code}\n")
            write_text(results / "delete-sandbox.error", exc.read().decode("utf-8", "replace"))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(item["rc"] != 0 for item in summary) else 0


if __name__ == "__main__":
    sys.exit(main())
