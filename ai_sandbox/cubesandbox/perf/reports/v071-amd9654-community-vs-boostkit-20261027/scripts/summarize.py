#!/usr/bin/env python3
"""Summarize cube-perf-bench community-native result dirs into one comparison CSV.

Usage: python3 -I summarize.py <out.csv> <label>=<phase-dir> [<label>=<phase-dir> ...]

Each phase dir holds one sub-directory per case (stdout.log, exit-code, and
cube-bench.json for startup cases) plus c100-{warmup,1..5}. Read-only on inputs.
"""
import csv, json, statistics, sys
from pathlib import Path

HEADERS = {  # first column set of each upstream script (later tiers use --no-header)
    "snapshot": "concurrency rounds wall_avg wall_min wall_p95 wall_max per_avg",
    "rollback": "concurrency rounds wall_avg wall_min wall_p95 wall_max per_avg",
    "create": "concurrency n_total rounds wall_avg wall_min wall_p95 wall_max per_avg",
    "clone": "n conc rounds wall_avg wall_min wall_p95 wall_max per_avg",
    "dirty": "write_MB dirty_MB_avg snap_avg snap_min snap_p95 snap_max create_avg create_min create_p95 create_max",
    "pause": "concurrency rounds pause_avg pause_min pause_p95 pause_max per_pause resume_avg resume_min resume_p95 resume_max per_resume",
}
KEYS = {  # metrics reported per family, in ms
    "snapshot": ["wall_avg", "wall_p95", "per_avg"], "rollback": ["wall_avg", "wall_p95", "per_avg"],
    "create": ["wall_avg", "wall_p95", "per_avg"], "clone": ["wall_avg", "wall_p95", "per_avg"],
    "dirty": ["snap_avg", "snap_p95", "create_avg", "create_p95", "dirty_MB_avg"],
    "pause": ["pause_avg", "pause_p95", "resume_avg", "resume_p95"],
}


def family(case):
    return "pause" if case.startswith(("pause", "extended-pause")) else case.split("-")[0]


def native_row(d, fam):
    lines = [l for l in (d / "stdout.log").read_text().splitlines() if l.strip()]
    data = [l.split() for l in lines if l.split() and all(_num(x) for x in l.split())]
    if not data:
        return {}
    row = dict(zip(HEADERS[fam].split(), data[-1]))
    return {k: float(row[k]) for k in KEYS[fam] if k in row}


def _num(x):
    try:
        float(x)
        return True
    except ValueError:
        return False


def startup(d):
    j = json.loads((d / "cube-bench.json").read_text())
    s, c = j["summary"], j["create"]
    return {"ok": f'{s["successful"]}/{s["successful"] + s["errors"]}', "total_ms": s["total_time_s"] * 1000,
            "avg": c["avg"], "p50": c["p50"], "p95": c["p95"], "p99": c["p99"], "max": c["max"]}


rows, out = [], Path(sys.argv[1])
for arg in sys.argv[2:]:
    label, phase = arg.split("=", 1)
    phase = Path(phase)
    for d in sorted(p for p in phase.iterdir() if p.is_dir() and (p / "stdout.log").exists()):
        case = d.name
        rc = (d / "exit-code").read_text().strip() if (d / "exit-code").exists() else "?"
        if case.startswith("c100-"):
            continue
        if (d / "cube-bench.json").exists():
            m = startup(d)
        else:
            m = native_row(d, family(case))
        rows.append({"phase": label, "case": case, "rc": rc, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items()}})
    c100 = [startup(phase / f"c100-{r}") for r in range(1, 6) if (phase / f"c100-{r}" / "cube-bench.json").exists()]
    if c100:
        for k in ("total_ms", "avg", "p95", "p99"):
            vals = [x[k] for x in c100]
            rows.append({"phase": label, "case": f"c100n100 x{len(vals)} {k}", "rc": "",
                         "median": round(statistics.median(vals), 1), "min": round(min(vals), 1),
                         "max": round(max(vals), 1), "rounds": " / ".join(f"{v:.1f}" for v in vals)})
cols = []
for r in rows:
    cols += [k for k in r if k not in cols]
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, cols)
    w.writeheader()
    w.writerows(rows)
print("wrote", out, len(rows), "rows")
