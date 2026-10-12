#!/usr/bin/env python3
"""Read-only local Cubelet quiet gate; does not generate benchmark requests."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    options = (
        ("tap-url", "TAP_URL", str, "http://127.0.0.1:9998/v1/network/taps"),
        ("task-root", "TASK_ROOT", str, "/data/cubelet/root/io.containerd.runtime.v2.task"),
        ("min-ready", "TAP_MIN_READY", int, 500),
        ("max-load", "MAX_LOAD", float, 5),
        ("samples", "QUIET_SAMPLES", int, 5),
        ("interval", "GATE_INTERVAL", float, 5),
        ("timeout", "GATE_TIMEOUT", float, 900),
        ("data-path", "DATA_PATH", str, "/data/cubelet"),
        ("log-path", "LOG_PATH", str, "/data/log"),
        ("data-reserve-gib", "DATA_RESERVE_GIB", float, 20),
        ("log-reserve-gib", "LOG_RESERVE_GIB", float, 8),
    )
    for flag, env, kind, default in options:
        p.add_argument("--" + flag, type=kind, default=os.environ.get("CUBE_PERF_" + env, default),
                       help=f"default {default}; environment CUBE_PERF_{env}; CLI overrides environment")
    return p


def reasons(sample, args):
    failures = []
    if sample["load1"] >= args.max_load:
        failures.append("load1")
    if sample["blocked"]:
        failures.append("blocked_tasks")
    for key in ("kvm_holders", "runtime_tasks", "cube_shims", "busy_processes"):
        if sample[key]:
            failures.append(key)
    counts = sample["tap_states"]
    if counts.get("Ready", 0) < args.min_ready or any(value for key, value in counts.items() if key != "Ready"):
        failures.append("tap_pool")
    if sample["data_free_bytes"] < args.data_reserve_gib * 1024**3:
        failures.append("data_disk")
    if sample["log_free_bytes"] < args.log_reserve_gib * 1024**3:
        failures.append("log_disk")
    return failures


def sample_host(args):
    root = Path(args.task_root)
    if not root.is_dir():
        raise RuntimeError(f"runtime task root missing: {root}")
    if not Path("/dev/kvm").exists():
        raise RuntimeError("/dev/kvm missing")
    usage = subprocess.run(["fuser", "/dev/kvm"], capture_output=True, text=True, timeout=5)
    if usage.returncode not in (0, 1) or (usage.returncode == 1 and usage.stderr.strip()):
        raise RuntimeError("KVM ownership inspection failed")
    processes = subprocess.check_output(["ps", "-eo", "pid=,comm="], text=True, timeout=5)
    busy, shims = [], []
    for line in processes.splitlines():
        pid, name = line.split(maxsplit=1)
        try:
            executable = Path(os.readlink(f"/proc/{pid}/exe")).name.removesuffix(" (deleted)")
        except (FileNotFoundError, ProcessLookupError):
            executable = ""
        if executable.startswith("containerd-shim-cube"):
            shims.append(int(pid))
        if name in {"cube-bench", "rustc", "cargo", "cc1", "cc1plus", "gcc", "g++",
                    "clang", "ninja", "make", "go", "fio", "stress", "stress-ng"} or name.startswith("qemu-system"):
            busy.append({"pid": int(pid), "comm": name})
    stat = dict(line.split(maxsplit=1) for line in Path("/proc/stat").read_text().splitlines())
    with urlopen(args.tap_url, timeout=5) as response:
        counts = json.load(response).get("stateCounts")
    if not isinstance(counts, dict) or not counts or any(type(value) is not int or value < 0 for value in counts.values()):
        raise RuntimeError("invalid TAP stateCounts")
    return {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "load1": float(Path("/proc/loadavg").read_text().split()[0]),
        "blocked": int(stat["procs_blocked"]),
        "kvm_holders": usage.stdout.split(),
        "runtime_tasks": sorted(str(path) for path in root.glob("*/*") if path.is_dir()),
        "cube_shims": shims,
        "busy_processes": busy,
        "tap_states": counts,
        "data_free_bytes": shutil.disk_usage(args.data_path).free,
        "log_free_bytes": shutil.disk_usage(args.log_path).free,
    }


def main(argv=None):
    args = parser().parse_args(argv)
    values = (args.max_load, args.interval, args.timeout, args.data_reserve_gib, args.log_reserve_gib)
    if args.samples < 1 or args.min_ready < 1 or any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("gate thresholds must be finite and positive")
    if os.geteuid() != 0:
        raise RuntimeError("gate requires root for complete local KVM ownership visibility")
    print(json.dumps({"kind": "configuration", **vars(args)}), flush=True)
    deadline, consecutive = time.monotonic() + args.timeout, 0
    while time.monotonic() < deadline:
        sample = sample_host(args)
        failed = reasons(sample, args)
        consecutive = consecutive + 1 if not failed else 0
        print(json.dumps({"kind": "sample", **sample, "failed": failed, "consecutive": consecutive}), flush=True)
        if consecutive >= args.samples:
            return 0
        time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
    raise RuntimeError("quiet gate deadline reached; no benchmark authorized by this gate")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"kind": "error", "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
