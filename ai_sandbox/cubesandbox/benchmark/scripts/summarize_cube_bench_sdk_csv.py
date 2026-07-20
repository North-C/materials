#!/usr/bin/env python3
"""Summarize cube_bench_sdk.py results into a CSV file.

Input is a result directory produced by scripts/cube_bench_sdk.py.
The primary CSV uses long format (one row per metric) and three compact
memory, prime, and language-runtime tables are generated alongside it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
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

TABLE_BASE_FIELDS = [
    "source",
    "results_dir",
    "case",
    "sandbox_id",
    "exit_code",
    "elapsed_sec",
]

TABLE_ARTIFACT_FIELDS = [
    "artifact",
    "copy_method",
    "warning",
    "error",
]

MEMORY_TABLE_FIELDS = [
    *TABLE_BASE_FIELDS,
    "mode",
    "access_mode",
    "operation",
    "throughput_mib_s",
    "transferred_mib",
    "events",
    "total_time_s",
    "latency_avg_ms",
    "latency_p95_ms",
    *TABLE_ARTIFACT_FIELDS,
]

PRIME_TABLE_FIELDS = [
    *TABLE_BASE_FIELDS,
    "max_prime",
    "events_per_sec",
    "total_events",
    "total_time_s",
    "latency_avg_ms",
    "latency_p95_ms",
    *TABLE_ARTIFACT_FIELDS,
]

RUNTIME_TABLE_FIELDS = [
    *TABLE_BASE_FIELDS,
    "runtime",
    "metric",
    "value",
    "unit",
    "aggregation",
    "subtest_count",
    "direction",
    *TABLE_ARTIFACT_FIELDS,
]

PYTHON_TIME_TO_MS = {
    "ns": Decimal("0.000001"),
    "us": Decimal("0.001"),
    "ms": Decimal("1"),
    "s": Decimal("1000"),
    "sec": Decimal("1000"),
}

JAVA_METRICS = (
    ("Composite", "composite"),
    ("FFT", "fft"),
    ("SOR", "sor"),
    ("Monte Carlo", "monte_carlo"),
    ("Sparse matmult", "sparse_matmult"),
    ("LU", "lu"),
)


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
    names = ("http", "json", "build", "garbage")
    values: dict[str, str] = {}

    for line in text.splitlines():
        try:
            payload = json.loads(line.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("case", "")).lower()
        benchmark = str(payload.get("benchmark", "")).lower()
        unit = str(payload.get("unit", "")).lower()
        value = payload.get("value")
        if name in names and benchmark == f"go-{name}-average" and unit == "ns/op" and value is not None:
            values[name] = str(value)

    for name in names:
        if name in values:
            continue
        samples = [
            Decimal(match.group(1))
            for match in re.finditer(
                rf"^Benchmark{re.escape(name)}\S*\s+\d+\s+([0-9.]+)\s+ns/op\b",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
        ]
        if samples:
            values[name] = decimal_text(sum(samples, Decimal("0")) / Decimal(len(samples)))

    for name in names:
        add_metric(rows, base, "go-benchmark", f"{name}_average_ns_op", values.get(name), "ns/op")


def parse_php(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    add_metric(rows, base, "php-benchmark", "score", first_match(r"(?:score|total score)[^0-9]*([0-9.]+)", text), "score")
    add_metric(rows, base, "php-benchmark", "total_time_s", first_match(r"(?:total[_ ]time|time)[^0-9]*([0-9.]+)\s*s", text), "s")


def parse_python(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    for metric, value, unit in python_metrics(text):
        add_metric(rows, base, "python-benchmark", metric, value, unit)


def python_metrics(text: str) -> list[tuple[str, str, str]]:
    metrics: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    pattern = (
        r"^([A-Za-z0-9_]+):\s*(?:Mean \+- std dev:\s*)?([0-9.]+)\s*"
        r"(ns|us|\N{MICRO SIGN}s|ms|sec|s)\b"
    )
    for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
        metric = match.group(1)
        if metric in seen:
            continue
        unit = match.group(3).lower().replace("\N{MICRO SIGN}", "u")
        metrics.append((metric, match.group(2), unit))
        seen.add(metric)
    return metrics


def parse_node(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    add_metric(
        rows,
        base,
        "node-octane",
        "score",
        first_match(r"(?:Octane\s+Score|Score)(?:\s*\([^\r\n)]*\))?\s*:\s*([0-9.]+)", text),
        "score",
    )


def parse_java(rows: list[dict[str, str]], base: dict[str, str], text: str) -> None:
    for label, metric in JAVA_METRICS:
        value = first_match(rf"^{re.escape(label)}(?:\s+Score)?(?:\s*\([^\r\n:]*\))?\s*:\s*([0-9.]+)", text)
        add_metric(rows, base, "java-scimark", metric, value, "Mflops")


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


def table_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(field, "") for field in (*TABLE_BASE_FIELDS, *TABLE_ARTIFACT_FIELDS))


def table_base(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in (*TABLE_BASE_FIELDS, *TABLE_ARTIFACT_FIELDS)}


def grouped_metrics(rows: list[dict[str, str]], benchmark_prefix: str) -> list[dict[str, str]]:
    grouped: OrderedDict[tuple[str, ...], dict[str, str]] = OrderedDict()
    for row in rows:
        if not row.get("benchmark", "").startswith(benchmark_prefix):
            continue
        key = table_key(row)
        item = grouped.setdefault(key, table_base(row))
        item[row["metric"]] = row["value"]
        item["benchmark"] = row["benchmark"]
    return list(grouped.values())


def build_memory_table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    table: list[dict[str, str]] = []
    for item in grouped_metrics(rows, "sysbench-memory:"):
        mode = item.pop("benchmark").split(":", 1)[1]
        access_mode, _, operation = mode.partition("-")
        item.update({"mode": mode, "access_mode": access_mode, "operation": operation})
        table.append(item)
    return table


def build_prime_table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    table: list[dict[str, str]] = []
    for item in grouped_metrics(rows, "sysbench-prime:"):
        benchmark = item.pop("benchmark")
        item["max_prime"] = item.get("max_prime") or benchmark.split(":", 1)[1]
        table.append(item)
    return table


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def build_runtime_table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    table: list[dict[str, str]] = []
    python_cases: OrderedDict[tuple[str, ...], dict[str, Any]] = OrderedDict()

    for row in rows:
        benchmark = row.get("benchmark", "")
        if benchmark == "go-benchmark":
            metric = row["metric"].removesuffix("_average_ns_op")
            table.append(
                {
                    **table_base(row),
                    "runtime": "Go",
                    "metric": metric,
                    "value": row["value"],
                    "unit": "ns/op",
                    "aggregation": "average",
                    "subtest_count": "1",
                    "direction": "lower_is_better",
                }
            )
        elif benchmark == "php-benchmark" and row.get("metric") == "score":
            table.append(
                {
                    **table_base(row),
                    "runtime": "PHP",
                    "metric": "score",
                    "value": row["value"],
                    "unit": "score",
                    "aggregation": "reported",
                    "subtest_count": "1",
                    "direction": "higher_is_better",
                }
            )
        elif benchmark == "python-benchmark":
            key = table_key(row)
            item = python_cases.setdefault(key, {"base": table_base(row), "metrics": OrderedDict()})
            item["metrics"].setdefault(row["metric"], (row["value"], row["unit"]))
        elif benchmark == "node-octane" and row.get("metric") == "score":
            table.append(
                {
                    **table_base(row),
                    "runtime": "Node.js",
                    "metric": "octane_score",
                    "value": row["value"],
                    "unit": "score",
                    "aggregation": "reported",
                    "subtest_count": "1",
                    "direction": "higher_is_better",
                }
            )
        elif benchmark == "java-scimark":
            table.append(
                {
                    **table_base(row),
                    "runtime": "Java",
                    "metric": row["metric"],
                    "value": row["value"],
                    "unit": "Mflops",
                    "aggregation": "reported",
                    "subtest_count": "1",
                    "direction": "higher_is_better",
                }
            )

    for item in python_cases.values():
        total_ms = Decimal("0")
        included = 0
        for value, unit in item["metrics"].values():
            try:
                total_ms += Decimal(value) * PYTHON_TIME_TO_MS[unit]
            except (InvalidOperation, KeyError):
                continue
            included += 1
        if included:
            table.append(
                {
                    **item["base"],
                    "runtime": "Python",
                    "metric": "subtests_total_time",
                    "value": decimal_text(total_ms),
                    "unit": "ms",
                    "aggregation": "sum_of_unique_subtest_means",
                    "subtest_count": str(included),
                    "direction": "lower_is_better",
                }
            )
    runtime_order = {"Go": 0, "PHP": 1, "Python": 2, "Node.js": 3, "Java": 4}
    table.sort(key=lambda row: runtime_order.get(row["runtime"], len(runtime_order)))
    return table


def write_table_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def related_output_path(output: Path, table: str) -> Path:
    suffix = output.suffix or ".csv"
    stem = output.stem if output.suffix else output.name
    return output.with_name(f"{stem}-{table}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, help="Result directory produced by cube_bench_sdk.py.")
    parser.add_argument("--output", help="Output CSV path. Defaults to <results-dir>/summary.csv.")
    parser.add_argument("--no-status", action="store_true", help="Do not include per-case exit_code/elapsed rows.")
    parser.add_argument("--memory-output", help="Memory table CSV. Defaults to <output-stem>-memory.csv.")
    parser.add_argument("--prime-output", help="Prime table CSV. Defaults to <output-stem>-prime.csv.")
    parser.add_argument("--runtime-output", help="Runtime table CSV. Defaults to <output-stem>-runtimes.csv.")
    parser.add_argument("--no-extra-tables", action="store_true", help="Only write the original long-format CSV.")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    output = Path(args.output).resolve() if args.output else results_dir / "summary.csv"
    rows = summarize(results_dir, include_status=not args.no_status)
    write_csv(output, rows)

    outputs: dict[str, str] = {"summary": str(output)}
    row_counts: dict[str, int] = {"summary": len(rows)}
    if not args.no_extra_tables:
        memory_output = Path(args.memory_output).resolve() if args.memory_output else related_output_path(output, "memory")
        prime_output = Path(args.prime_output).resolve() if args.prime_output else related_output_path(output, "prime")
        runtime_output = Path(args.runtime_output).resolve() if args.runtime_output else related_output_path(output, "runtimes")
        memory_rows = build_memory_table(rows)
        prime_rows = build_prime_table(rows)
        runtime_rows = build_runtime_table(rows)
        write_table_csv(memory_output, memory_rows, MEMORY_TABLE_FIELDS)
        write_table_csv(prime_output, prime_rows, PRIME_TABLE_FIELDS)
        write_table_csv(runtime_output, runtime_rows, RUNTIME_TABLE_FIELDS)
        outputs.update({"memory": str(memory_output), "prime": str(prime_output), "runtimes": str(runtime_output)})
        row_counts.update({"memory": len(memory_rows), "prime": len(prime_rows), "runtimes": len(runtime_rows)})

    print(
        json.dumps(
            {
                "output": str(output),
                "rows": len(rows),
                "outputs": outputs,
                "row_counts": row_counts,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
