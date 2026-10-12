#!/usr/bin/env python3
"""Read-only audit of one native bench-core exec_only, one-round result directory.

No API calls, workload execution or cleanup. CLI success does not prove that
foreign resources were preserved: verify the external ownership inventory too.
"""
import argparse
import csv
import json
from pathlib import Path


def executable_count(path):
    raw = json.loads(path.read_text())
    count = 0
    for step in raw.get("trajectory", []):
        words = str(step.get("action") or "").strip().split()
        if words and words[0] in {"submit", "finish", "done"}:
            break
        count += 1
    return raw.get("instance_id") or path.stem, count


def audit(run_dir, expected_count, expected_distinct, trajectories, require_monitor,
          max_timeout_run_fraction, cpu_budget=None, vcpus=2):
    errors = []
    summaries = list(run_dir.glob("*_run_summary.json"))
    if len(summaries) != 1:
        raise ValueError("give the timestamped run directory containing exactly one run_summary")
    summary = json.loads(summaries[0].read_text())
    report_path = (summary.get("paths") or {}).get("report")
    if not report_path or not (run_dir / Path(report_path).name).is_file():
        errors.append("native final report missing (possibly an interrupted/partial run)")
    if not (run_dir / "trajectories/index.json").is_file():
        errors.append("trajectory index missing")
    if summary.get("replay_mode") != "exec_only":
        errors.append("this checker accepts exec_only only")
    if summary.get("error"):
        errors.append("native summary reports an error")
    throughput = summary.get("throughput") or {}
    if summary.get("total_count") != expected_count:
        errors.append("configured sandbox count differs from expected")
    for key in ("total", "succeeded"):
        if throughput.get(key) != expected_count:
            errors.append(f"trajectory {key} differs from expected_count")
    if throughput.get("failed") != 0:
        errors.append("one or more trajectories did not complete")
    expected = dict(executable_count(p) for p in trajectories.glob("*.replay.json"))
    if not expected:
        errors.append("input trajectory directory is empty")
    records = [json.loads(p.read_text()) for p in run_dir.glob("trajectories/*/replay_result.json")]
    if len(records) != expected_distinct:
        errors.append(f"distinct trajectory count {len(records)} != {expected_distinct}")
    seen = set()
    steps_total = nonzero = timeout_steps = infra_steps = timeout_runs = failed_runs = 0
    for record in records:
        tid = record.get("trajectory_id")
        if tid not in expected:
            errors.append(f"trajectory is absent from input data: {tid}")
        for run in record.get("runs", []):
            key = (tid, run.get("sandbox_index"), run.get("round_id"))
            if key in seen:
                errors.append(f"duplicate run key: {key}")
            seen.add(key)
            steps = run.get("steps", [])
            indices = [s.get("index") for s in steps]
            if tid in expected and indices != list(range(expected[tid])):
                errors.append(f"missing/reordered steps: {key}")
            if run.get("create_error_type") or run.get("kill_error_type"):
                errors.append(f"create/kill error: {key}")
            t = sum(bool(s.get("timed_out")) for s in steps)
            # Native exports mark a timeout as slice_failed too. Do not count
            # it a second time as a non-timeout execution-layer failure.
            i = sum(bool(s.get("slice_failed")) and not s.get("timed_out") for s in steps)
            steps_total += len(steps)
            nonzero += sum(s.get("return_code") not in (0, None) for s in steps)
            timeout_steps += t
            infra_steps += i
            timeout_runs += bool(t)
            failed_runs += bool(t or i or run.get("create_error_type") or run.get("kill_error_type"))
    if len(seen) != expected_count:
        errors.append(f"actual runs {len(seen)} != {expected_count}")
    if steps_total != throughput.get("total_steps"):
        errors.append("step export count differs from native summary")
    series_files = list(run_dir.glob("*_lifecycle_series.jsonl"))
    series_steps = 0
    if len(series_files) != 1:
        errors.append("expected one native series")
    else:
        with series_files[0].open() as f:
            for line in f:
                if json.loads(line).get("event") == "step":
                    series_steps += 1
        if series_steps != steps_total:
            errors.append("series/export step counts differ")
    monitor_rows = 0
    monitor_csv = run_dir / "vm_monitor/cubesandbox_monitor.csv"
    if monitor_csv.is_file():
        with monitor_csv.open(encoding="utf-8-sig", newline="") as f:
            monitor_rows = sum(1 for _ in csv.DictReader(f))
    monitor_present = bool(summary.get("paths", {}).get("vm_monitor_dir")) and monitor_rows > 0
    if require_monitor and not monitor_present:
        errors.append("required VM monitor missing or empty")
    timeout_fraction = timeout_runs / len(seen) if seen else 1.0
    quality_ok = timeout_fraction <= max_timeout_run_fraction and infra_steps == 0
    return {
        "run_dir": str(run_dir), "data_complete": not errors, "errors": errors,
        "quality_gate_passed": quality_ok,
        "timeout_run_fraction_limit": max_timeout_run_fraction,
        "trajectory_runs": len(seen), "distinct_trajectories": len(records),
        "steps": steps_total, "nonzero_return_codes": nonzero,
        "timed_out_steps": timeout_steps, "timeout_runs": timeout_runs,
        "non_timeout_slice_failed_steps": infra_steps, "failed_runs": failed_runs,
        "timeout_run_fraction": timeout_fraction,
        "native_wall_sec": summary.get("wall_sec"),
        "native_steps_per_sec": throughput.get("steps_per_sec"),
        "native_overcommit_ratio": summary.get("overcommit_ratio"),
        "configured_cpu_overcommit": expected_count * vcpus / cpu_budget if cpu_budget else None,
        "monitor_rows": monitor_rows, "monitor_present": monitor_present,
        "cleanup_verified": False,
        "scope": "one round exec_only; cleanup and observed VM concurrency require separate live inventory/monitor checks",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_dir", type=Path)
    p.add_argument("--expected-count", required=True, type=int)
    p.add_argument("--expected-distinct", required=True, type=int)
    p.add_argument("--trajectories", required=True, type=Path)
    p.add_argument("--require-monitor", action="store_true")
    p.add_argument("--max-timeout-run-fraction", default=0.0, type=float)
    p.add_argument("--cpu-budget", type=float)
    p.add_argument("--vcpus", type=float, default=2)
    a = p.parse_args()
    if min(a.expected_count, a.expected_distinct) < 1 or not 0 <= a.max_timeout_run_fraction <= 1:
        p.error("counts must be positive; fraction must be in [0,1]")
    if a.vcpus <= 0 or (a.cpu_budget is not None and a.cpu_budget <= 0):
        p.error("CPU budgets must be positive")
    try:
        result = audit(a.run_dir.resolve(), a.expected_count, a.expected_distinct,
                       a.trajectories.resolve(), a.require_monitor,
                       a.max_timeout_run_fraction, a.cpu_budget, a.vcpus)
    except (ValueError, OSError, KeyError) as exc:
        p.exit(2, f"audit error: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["data_complete"] and result["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
