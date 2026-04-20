#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIMARY_METRICS = [
    "request_to_running_seconds",
    "sandbox_create_seconds",
    "vm_boot_seconds",
    "vm_to_agent_seconds",
    "create_container_seconds",
    "start_container_seconds",
]


VALIDATION_FIELDS = [
    "validation_snapshotter_is_nydus",
    "validation_kata_config_is_clh",
    "validation_effective_image_matches_request",
    "validation_nydus_log_seen",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot compute percentile from empty series")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def summarize_numeric(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p90": _percentile(ordered, 0.90),
        "p99": _percentile(ordered, 0.99),
    }


def collect_run_sample_result(run_dir: Path) -> dict[str, Any]:
    result = _load_json(Path(run_dir) / "summary" / "result.json", {})
    return {
        "run_dir": str(Path(run_dir)),
        "run_id": result.get("run_id", ""),
        "workload_type": result.get("workload_type", "direct_kata_container"),
        "runtime_handler": result.get("runtime_handler", ""),
        "hypervisor": result.get("hypervisor", ""),
        "snapshotter": result.get("snapshotter", ""),
        "source_image": result.get("source_image", ""),
        "effective_image": result.get("effective_image", ""),
        "request_to_running_seconds": result.get("request_to_running_seconds", ""),
        "sandbox_create_seconds": result.get("sandbox_create_seconds", ""),
        "vm_boot_seconds": result.get("vm_boot_seconds", ""),
        "vm_to_agent_seconds": result.get("vm_to_agent_seconds", ""),
        "create_container_seconds": result.get("create_container_seconds", ""),
        "start_container_seconds": result.get("start_container_seconds", ""),
        "validation_snapshotter_is_nydus": bool(
            result.get("validation_snapshotter_is_nydus")
        ),
        "validation_kata_config_is_clh": bool(result.get("validation_kata_config_is_clh")),
        "validation_effective_image_matches_request": bool(
            result.get("validation_effective_image_matches_request")
        ),
        "validation_nydus_log_seen": bool(result.get("validation_nydus_log_seen")),
    }


def _summary_validation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = 0
    per_field_success: dict[str, int] = {name: 0 for name in VALIDATION_FIELDS}
    for row in rows:
        field_values = [bool(row.get(name)) for name in VALIDATION_FIELDS]
        if all(field_values):
            success_count += 1
        for field_name in VALIDATION_FIELDS:
            if row.get(field_name):
                per_field_success[field_name] += 1
    return {
        "validation_success_count": success_count,
        "validation_failure_count": len(rows) - success_count,
        "validation_success_rate": (success_count / len(rows)) if rows else 0.0,
        "validation_field_success_counts": per_field_success,
    }


def summarize_batch_results(
    *,
    batch_id: str,
    sample_run_dirs: list[Path],
    warmup_run_dirs: list[Path],
) -> dict[str, Any]:
    sample_results = [collect_run_sample_result(Path(run_dir)) for run_dir in sample_run_dirs]

    metrics: dict[str, Any] = {}
    for metric_name in PRIMARY_METRICS:
        values = [
            float(row[metric_name])
            for row in sample_results
            if row.get(metric_name) not in ("", None)
        ]
        if values:
            metrics[metric_name] = summarize_numeric(values)

    summary = {
        "sample_count": len(sample_results),
        **_summary_validation(sample_results),
        "metrics": metrics,
    }

    return {
        "generated_at": utc_now(),
        "batch_id": batch_id,
        "sample_run_count": len(sample_run_dirs),
        "warmup_run_count": len(warmup_run_dirs),
        "sample_run_dirs": [str(Path(path)) for path in sample_run_dirs],
        "warmup_run_dirs": [str(Path(path)) for path in warmup_run_dirs],
        "sample_results": sample_results,
        "summary": summary,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_sample_results_csv(path: Path, sample_results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_id",
        "workload_type",
        "runtime_handler",
        "hypervisor",
        "snapshotter",
        "source_image",
        "effective_image",
        "request_to_running_seconds",
        "sandbox_create_seconds",
        "vm_boot_seconds",
        "vm_to_agent_seconds",
        "create_container_seconds",
        "start_container_seconds",
        "validation_snapshotter_is_nydus",
        "validation_kata_config_is_clh",
        "validation_effective_image_matches_request",
        "validation_nydus_log_seen",
        "run_dir",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sample_results:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_batch_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    fieldnames = [
        "sample_count",
        "validation_success_count",
        "validation_failure_count",
        "validation_success_rate",
        "request_to_running_seconds_mean",
        "request_to_running_seconds_p50",
        "request_to_running_seconds_p90",
        "request_to_running_seconds_p99",
        "sandbox_create_seconds_mean",
        "sandbox_create_seconds_p50",
        "sandbox_create_seconds_p90",
        "sandbox_create_seconds_p99",
        "vm_boot_seconds_mean",
        "vm_boot_seconds_p50",
        "vm_to_agent_seconds_mean",
        "create_container_seconds_mean",
        "start_container_seconds_mean",
    ]
    row = {
        "sample_count": summary.get("sample_count", 0),
        "validation_success_count": summary.get("validation_success_count", 0),
        "validation_failure_count": summary.get("validation_failure_count", 0),
        "validation_success_rate": summary.get("validation_success_rate", 0.0),
    }
    for metric_name in PRIMARY_METRICS:
        stats = summary.get("metrics", {}).get(metric_name, {})
        for stat_name in ("mean", "p50", "p90", "p99"):
            key = f"{metric_name}_{stat_name}"
            if key in fieldnames:
                row[key] = stats.get(stat_name, "")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


def write_batch_artifacts(batch_dir: Path, summary: dict[str, Any]) -> None:
    batch_dir = Path(batch_dir)
    summary_dir = batch_dir / "summary"
    _write_json(summary_dir / "batch-results.json", summary)
    _write_sample_results_csv(summary_dir / "batch-sample-results.csv", summary["sample_results"])
    _write_batch_summary_csv(summary_dir / "batch-summary.csv", summary["summary"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate direct Nydus+Kata batch run results."
    )
    parser.add_argument("--batch-dir", required=True)
    parser.add_argument("--sample-run-dir", action="append", default=[])
    parser.add_argument("--warmup-run-dir", action="append", default=[])
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir)
    summary = summarize_batch_results(
        batch_id=batch_dir.name,
        sample_run_dirs=[Path(path) for path in args.sample_run_dir],
        warmup_run_dirs=[Path(path) for path in args.warmup_run_dir],
    )
    write_batch_artifacts(batch_dir, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
