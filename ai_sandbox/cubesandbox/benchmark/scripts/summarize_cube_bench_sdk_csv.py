#!/usr/bin/env python3
"""Summarize cube_bench_sdk.py results into a CSV file.

Input is a result directory produced by scripts/cube_bench_sdk.py.
The output CSV uses long format: one row per metric.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


CSV_FIELDS = [
    "source",
    "results_dir",
    "case",
    "sandbox_id",
    "sandbox_ip",
    "exit_code",
    "elapsed_sec",
    "benchmark",
    "metric",
    "value",
    "unit",
    "artifact",
    "copy_method",
    "warning",
    "error",
]


def first_match(pattern: str, text: str, group: int | str = 1) -> str:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    return str(match.group(group))


def add_metric(
    rows: list[dict[str, str]],
    base: dict[str, str],
    benchmark: str,
    metric: str,
    value: str | int | float | None,
    unit: str = "",
) -> None:
    if value is None or value == "":
        return
    row = dict(base)
    row.update({"benchmark": benchmark, "metric": metric, "value": str(value), "unit": unit})
    rows.append(row)


def log_path(results_dir: Path, item: dict[str, Any]) -> Path:
    case = str(item["case"])
    result_dir = Path(item.get("result_dir") or results_dir)
    candidates = [
        result_dir / f"{case}.log",
        result_dir / f"{case}.stdout.log",
        results_dir / case / f"{case}.log",
        results_dir / case / f"{case}.stdout.log",
        results_dir / f"{case}.log",
        results_dir / f"{case}.stdout.log",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_memory(rows: list[dict[str, str]], base: dict[str, str], case: str, text: str) -> None:
    mode = ""
    if "seq-read" in case:
        mode = "seq-read"
    elif "seq-write" in case:
        mode = "seq-write"
    elif "rnd-read" in case:
        mode = "rnd-read"
    elif "rnd-write" in case:
        mode = "rnd-write"
    benchmark = f"sysbench-memory:{mode or case}"
    add_metric(rows, base, benchmark, "transferred_mib", first_match(r"([0-9.]+)\s+MiB transferred", text), "MiB")
    add_metric(rows, base, benchmark, "throughput_mib_s", first_match(r"\(([0-9.]+)\s+MiB/sec\)", text), "MiB/s")
    add_metric(rows, base, benchmark, "events", first_match(r"total number of events:\s*([0-9]+)", text), "events")
    add_metric(rows, base, benchmark, "total_time_s", first_match(r"total time:\s*([0-9.]+)s", text), "s")
    add_metric(rows, base, benchmark, "latency_avg_ms", first_match(r"avg:\s*([0-9.]+)", text), "ms")
    add_metric(rows, base, benchmark, "latency_p95_ms", first_match(r"95th percentile:\s*([0-9.]+)", text), "ms")


def parse_prime(rows: list[dict[str, str]], base: dict[str, str], case: str, text: str) -> None:
    max_prime = first_match(r"sysbench-prime-([0-9]+)", case) or first_match(r"cpu-max-prime=([0-9]+)", text)
    benchmark = f"sysbench-prime:{max_prime or 'unknown'}"
    add_metric(rows, base, benchmark, "max_prime", max_prime, "")
    add_metric(rows, base, benchmark, "events_per_sec", first_match(r"events per second:\s*([0-9.]+)", text), "events/s")
    add_metric(rows, base, benchmark, "total_events", first_match(r"total number of events:\s*([0-9]+)", text), "events")
    add_metric(rows, base, benchmark, "total_time_s", first_match(r"total time:\s*([0-9.]+)s", text), "s")
    add_metric(rows, base, benchmark, "latency_avg_ms", first_match(r"avg:\s*([0-9.]+)", text), "ms")
    add_metric(rows, base, benchmark, "latency_p95_ms", first_match(r"95th percentile:\s*([0-9.]+)", text), "ms")


def parse_go(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    seen: set[str] = set()
    for name in ("http", "json", "build", "garbage"):
        patterns = [
            rf'"?{name}"?.*?"average[_-]?ns[_-]?per[_-]?op"?\s*[:=]\s*([0-9.]+)',
            rf"{name}.*?average.*?([0-9.]+)\s*ns/op",
            rf"{name}.*?([0-9.]+)\s*ns/op.*?average",
        ]
        for pattern in patterns:
            value = first_match(pattern, text)
            if value:
                add_metric(rows, base, "go-benchmark", f"{name}_average_ns_op", value, "ns/op")
                seen.add(name)
                break
    if seen:
        return
    for match in re.finditer(r"(http|json|build|garbage).*?([0-9.]+)\s*ns/op", text, re.IGNORECASE):
        name = match.group(1).lower()
        if name in seen:
            continue
        add_metric(rows, base, "go-benchmark", f"{name}_average_ns_op", match.group(2), "ns/op")
        seen.add(name)


def parse_php(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    add_metric(rows, base, "php-benchmark", "score", first_match(r"(?:score|total score)[^0-9]*([0-9.]+)", text), "score")
    add_metric(rows, base, "php-benchmark", "total_time_s", first_match(r"(?:total[_ ]time|time)[^0-9]*([0-9.]+)\s*s", text), "s")


def parse_python(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    for match in re.finditer(r"^([A-Za-z0-9_]+):\s*(?:Mean \+- std dev:\s*)?([0-9.]+)\s*([mun]?s|sec|ms)", text, re.MULTILINE):
        add_metric(rows, base, "python-benchmark", match.group(1), match.group(2), match.group(3))


def parse_node(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    add_metric(rows, base, "node-octane", "score", first_match(r"(?:Octane Score|Score):\s*([0-9.]+)", text), "score")


def parse_java(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    for metric in ("Composite", "FFT", "SOR", "Monte Carlo", "Sparse matmult", "LU"):
        value = first_match(rf"{re.escape(metric)}(?:\s+Score)?:\s*([0-9.]+)", text)
        add_metric(rows, base, "java-scimark", metric.lower().replace(" ", "_"), value, "score")


def parse_case(rows: list[dict[str, str]], base: dict[str, str], case: str, text: str) -> None:
    before = len(rows)
    if "sysbench-memory" in case:
        parse_memory(rows, base, case, text)
    elif "sysbench-prime" in case:
        parse_prime(rows, base, case, text)
    elif "go-benchmark" in case:
        parse_go(rows, base, text)
    elif "php-benchmark" in case:
        parse_php(rows, base, text)
    elif "python-benchmark" in case:
        parse_python(rows, base, text)
    elif "node-octane" in case:
        parse_node(rows, base, text)
    elif "java-scimark" in case:
        parse_java(rows, base, text)
    if len(rows) == before:
        add_metric(rows, base, "case", "parsed_metric_count", 0, "count")


def summarize(results_dir: Path, include_status: bool) -> list[dict[str, str]]:
    summary_path = results_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"summary.json not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for item in summary:
        case = str(item["case"])
        path = log_path(results_dir, item)
        copy_method = str(item.get("copy_method") or "")
        warning = str(item.get("warning") or "")
        error = str(item.get("error") or "")
        if str(item.get("exit_code", "")) == "0" and error.startswith("files.read("):
            warning = warning or error
            error = ""
            copy_method = copy_method or "sdk_stdout_fallback"
        base = {
            "source": "sdk",
            "results_dir": str(results_dir),
            "case": case,
            "sandbox_id": str(item.get("sandbox_id", "")),
            "sandbox_ip": "",
            "exit_code": str(item.get("exit_code", "")),
            "elapsed_sec": str(item.get("elapsed_sec", "")),
            "benchmark": "",
            "metric": "",
            "value": "",
            "unit": "",
            "artifact": str(path),
            "copy_method": copy_method,
            "warning": warning,
            "error": error,
        }
        if include_status:
            add_metric(rows, base, "case", "exit_code", item.get("exit_code", ""), "code")
            add_metric(rows, base, "case", "elapsed_sec", item.get("elapsed_sec", ""), "s")
        parse_case(rows, base, case, read_text(path))
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, help="Result directory produced by cube_bench_sdk.py.")
    parser.add_argument("--output", help="Output CSV path. Defaults to <results-dir>/summary.csv.")
    parser.add_argument("--no-status", action="store_true", help="Do not include per-case exit_code/elapsed rows.")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    output = Path(args.output).resolve() if args.output else results_dir / "summary.csv"
    rows = summarize(results_dir, include_status=not args.no_status)
    write_csv(output, rows)
    print(json.dumps({"output": str(output), "rows": len(rows), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
