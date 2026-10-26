#!/usr/bin/env python3
"""Derive per-round summaries from a five-round capture_100.py result directory.

Usage: python3 -I derive.py <result-dir> <output-dir>

<result-dir> has r1..r5/<run>/ from capture_100.py plus paired-host-boundaries.json
(from pair_host_boundaries.py). Reads benchmark.raw.json, analysis/stage-latency.csv
and capture/evidence/api-delta.log; writes three CSVs. Read-only on inputs; no
network or deployment access.
"""
import csv, datetime, glob, json, statistics, sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rounds = range(1, 6)
run = {r: Path(glob.glob(f"{src}/r{r}/*/")[0]) for r in rounds}
paired = {x["round"]: x for x in json.loads((src / "paired-host-boundaries.json").read_text())["runs"]}


def ts(s):
    """ISO-8601 with nanoseconds -> epoch ns (datetime only keeps microseconds)."""
    s = s.replace("Z", "+00:00")
    head, rest = s.split(".", 1)
    frac, tz = rest[:-6], rest[-6:]
    return int(datetime.datetime.fromisoformat(head + tz).timestamp()) * 10**9 + int(frac.ljust(9, "0")[:9])


# 1. Client-side round summary (cube-bench formal JSON, w0, c100 n100).
with open(out / "round-summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["round", "successful", "errors", "total_time_ms", "create_min_ms", "create_avg_ms",
                "create_p50_ms", "create_p90_ms", "create_p95_ms", "create_p99_ms", "create_max_ms", "create_std_ms"])
    for r in rounds:
        raw = json.loads((run[r] / "capture/startup-latency/benchmark.raw.json").read_text())
        c, s = raw["create"], raw["summary"]
        w.writerow([r, s["successful"], s["errors"], round(s["total_time_s"] * 1000, 3),
                    *[round(c[k], 3) for k in ("min", "avg", "p50", "p90", "p95", "p99", "max", "std")]])

# 2. Formal-phase stage statistics, one row per (component, stage) and round.
with open(out / "stage-summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["component", "stage", "parent_stage_id", "timing_kind", "round", "avg_ms", "p95_ms", "observed_instances"])
    for r in rounds:
        for d in csv.DictReader(open(run[r] / "analysis/stage-latency.csv")):
            if d["phase"] == "formal" and d["avg_ms"]:
                w.writerow([d["component"], d["stage"], d["parent_stage_id"], d["timing_kind"], r,
                            round(float(d["avg_ms"]), 3), round(float(d["p95_ms"] or 0), 3),
                            d["observed_instances"] or d["count"]])

# 3. Pre-Master estimate. CubeAPI logs only sandbox.created at completion, so the
#    client start t0 is approximated as (last sandbox.created - total_time_s).
with open(out / "pre-master-estimate.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["round", "total_time_ms", "first_master_start_after_t0_ms", "master_start_spread_ms",
                "pre_master_avg_ms", "pre_master_max_ms", "master_reply_to_api_created_avg_ms",
                "master_reply_to_api_created_p95_ms", "paired"])
    for r in rounds:
        raw = json.loads((run[r] / "capture/startup-latency/benchmark.raw.json").read_text())
        total = raw["summary"]["total_time_s"] * 1e9
        api = {}
        for line in open(run[r] / "capture/evidence/api-delta.log"):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("event") == "sandbox.created":
                api[j["sandbox_id"]] = ts(j["timestamp"])
        rows = [x for x in paired[r]["rows"] if x["sandbox_id"] in api]
        t0 = max(api[x["sandbox_id"]] for x in rows) - total
        starts = [x["boundaries_ns"]["master_start"] for x in rows]
        pre = [(s - t0) / 1e6 for s in starts]
        gap = sorted((api[x["sandbox_id"]] - x["boundaries_ns"]["master_reply"]) / 1e6 for x in rows)
        w.writerow([r, round(total / 1e6, 3), round((min(starts) - t0) / 1e6, 3),
                    round((max(starts) - min(starts)) / 1e6, 3), round(statistics.mean(pre), 3),
                    round(max(pre), 3), round(statistics.mean(gap), 3), round(gap[int(len(gap) * .95) - 1], 3), len(rows)])
print("wrote", *(p.name for p in sorted(out.glob("*.csv"))))
