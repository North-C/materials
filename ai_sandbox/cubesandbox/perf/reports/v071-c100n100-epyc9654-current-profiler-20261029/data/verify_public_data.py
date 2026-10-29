#!/usr/bin/env python3
"""Read-only checks of this public data directory; Python 3 standard library only."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10), "numeric mismatch"


def main():
    comparison = read("comparison.json")
    rounds = comparison["rounds"]
    assert len(rounds) == 15
    assert all(r["successful"] == 100 and r["errors"] == 0 for r in rounds)
    with (ROOT / "rounds.csv").open() as stream:
        csv_rounds = list(csv.DictReader(stream))
    assert len(csv_rounds) == len(rounds)
    for a, b in zip(rounds, csv_rounds):
        assert set(a) == set(b)
        for key, value in a.items():
            if isinstance(value, (int, float)):
                close(value, float(b[key]))
            else:
                assert value == b[key]
    metrics = ("wall_ms", "request_mean_ms", "request_p95_ms", "request_max_ms")
    for group in ("B", "D", "F"):
        selected = [r for r in rounds if r["group"] == group]
        assert len(selected) == 5
        for metric in metrics:
            values = [r[metric] for r in selected]
            stored = comparison["groups"][group][metric]
            assert values == stored["values"]
            for key, value in (("mean", statistics.mean(values)), ("median", statistics.median(values)),
                               ("min", min(values)), ("max", max(values))):
                close(value, stored[key])
    deltas = []
    for pair in comparison["paired_F_minus_D"]:
        selected = {r["group"]: r for r in rounds if r["group"] in ("D", "F") and r["pair"] == pair["pair"]}
        delta = selected["F"]["wall_ms"] - selected["D"]["wall_ms"]
        close(delta, pair["F_minus_D_ms"])
        deltas.append(delta)
    contrast = comparison["contrast"]
    d = comparison["groups"]["D"]["wall_ms"]["median"]
    f = comparison["groups"]["F"]["wall_ms"]["median"]
    close(f - d, contrast["median_difference_ms"])
    close((f / d - 1) * 100, contrast["median_change_percent"])
    close(statistics.mean(deltas), contrast["paired_mean_ms"])
    assert [min(deltas), max(deltas)] == contrast["paired_range_ms"]
    with (ROOT / "stage-rounds.csv").open() as stream:
        stage_rows = list(csv.DictReader(stream))
    assert len(stage_rows) == 990
    index = {(r["round"], r["phase"], r["name"]): r for r in stage_rows}
    assert len(index) == len(stage_rows)
    summary = read("stage-summary.json")
    assert summary["completed_captures"] == summary["expected_captures"] == 5
    for stage in summary["stages"]:
        means, p95s = [], []
        for round_name, coverage in stage["round_coverage"].items():
            row = index[round_name, stage["phase"], stage["name"]]
            assert int(row["n"]) == coverage["n"] and int(row["instances"]) == coverage["instances"]
            assert json.loads(row["excluded"]) == coverage["excluded"]
            if coverage["instances"]:
                close(float(row["coverage"]), coverage["n"] / coverage["instances"])
            if row["mean_ms"]:
                means.append(float(row["mean_ms"]))
                p95s.append(float(row["p95_ms"]))
        assert stage["rounds_with_measurement"] == len(means)
        for value in stage["round_values"]:
            row = index[value["round"], stage["phase"], stage["name"]]
            for key in ("mean_ms", "p95_ms", "max_ms"):
                assert (float(row[key]) if row[key] else None) == value[key]
        if means:
            for key, value in (("mean_of_round_means_ms", statistics.mean(means)),
                               ("median_of_round_means_ms", statistics.median(means)),
                               ("min_round_mean_ms", min(means)), ("max_round_mean_ms", max(means)),
                               ("median_of_round_p95_ms", statistics.median(p95s))):
                close(value, stage[key])
        else:
            assert stage["median_of_round_means_ms"] is None
    stages = {(x["phase"], x["name"]): x for x in summary["stages"]}
    for phase, expected in (("formal", 500), ("warmup", 15)):
        for name in ("client.create_headers", "cubelet_start_to_resolved", "master.templateresolve", "master.cube-e2e"):
            assert sum(v["n"] for v in stages[phase, name]["round_coverage"].values()) == expected
    storage = stages["formal", "cubelet.storage"]["round_coverage"]
    assert [storage[f"F-r{i}"]["n"] for i in range(1, 6)] == [74, 73, 86, 82, 73]
    assert sum(v["n"] for v in storage.values()) == 388
    assert all(int(x["n"]) == 0 for x in stage_rows if x["name"].startswith("frontdoor."))
    assert all(int(x["instances"]) == 0 for x in stage_rows if x["phase"] == "unknown_phase")
    tails = read("tail-summary.json")["requests"]
    assert len(tails) == 5
    for i, (tail, seq) in enumerate(zip(tails, (16, 94, 36, 55, 40)), 1):
        assert tail["round"] == f"F-r{i}" and tail["seq"] == seq and tail["phase"] == "formal"
        assert tail["request_alias"] == f"F-r{i}-formal-rank-1" and tail["client_latency_rank"] == 1
        close(tail["client_ms"], next(r["request_max_ms"] for r in rounds if r["id"] == f"F-r{i}"))
    for row in read("f5-stage-variation.json"):
        values = stages["formal", row["stage"]]["round_values"]
        first = statistics.mean(x["mean_ms"] for x in values if x["round"] != "F-r5")
        last = next(x for x in values if x["round"] == "F-r5")
        close(first, row["first_four_round_means_average_ms"])
        close(last["mean_ms"], row["f5_mean_ms"])
        close(last["mean_ms"] - first, row["difference_ms"])
        close(last["p95_ms"], row["f5_p95_ms"])
    checked_hashes = 0
    for line in (ROOT / "DATA-PROJECTION.zh-CN.md").read_text().splitlines():
        match = re.fullmatch(r"\| \[([^]]+)\]\([^)]*\) \| .* \| `([0-9a-f]{64})` \|", line)
        if match:
            assert hashlib.sha256((ROOT / match[1]).read_bytes()).hexdigest() == match[2], "public SHA mismatch"
            checked_hashes += 1
    assert checked_hashes == 7
    print(json.dumps({"status": "pass", "rounds": 15, "stage_rows": 990,
                      "formal_core_coverage": 500, "warmup_core_coverage": 15,
                      "storage_observed": 388, "storage_missing": 112,
                      "tail_requests": 5, "public_hashes_checked": checked_hashes}))


if __name__ == "__main__":
    main()
