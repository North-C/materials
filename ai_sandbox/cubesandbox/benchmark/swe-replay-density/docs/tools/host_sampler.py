#!/usr/bin/env python3
"""Dependency-free host resource sampler for .90 density rounds.

Samples every N seconds into a CSV: CPU util, memory, load, running VM (cube-shim)
count, pressure info. Belt-and-suspenders alongside vm-monitor (cubesandbox).

Usage: host_sampler.py <output.csv> [interval_sec]
Stop with SIGTERM/SIGINT (flushes and exits cleanly).
"""
import csv
import datetime
import signal
import subprocess
import sys
import time

OUT = sys.argv[1]
INTERVAL = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
_running = True

def _stop(signum, frame):
    global _running
    _running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

_prev_cpu = None

def cpu_util():
    global _prev_cpu
    fields = open("/proc/stat").readline().split()[1:]
    vals = [int(x) for x in fields]  # user nice system idle iowait irq softirq steal
    idle = vals[3] + vals[4]
    total = sum(vals)
    if _prev_cpu is None:
        _prev_cpu = (idle, total)
        return 0.0
    didle = idle - _prev_cpu[0]
    dtotal = total - _prev_cpu[1]
    _prev_cpu = (idle, total)
    if dtotal <= 0:
        return 0.0
    return round(100.0 * (dtotal - didle) / dtotal, 2)

def meminfo():
    d = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        d[k] = int(v.strip().split()[0])
    return d

def shim_count():
    try:
        r = subprocess.run(["pgrep", "-c", "-f", "containerd-shim-cube-rs"],
                           capture_output=True, text=True, timeout=10)
        return int(r.stdout.strip()) if r.returncode == 0 else 0
    except Exception:
        return -1

FIELDS = ["ts", "cpu_util_pct", "mem_available_mb", "mem_used_mb", "mem_cached_mb",
          "swap_used_mb", "load1", "load5", "vm_shim_count", "procs_running"]

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    while _running:
        m = meminfo()
        load1, load5 = open("/proc/loadavg").read().split()[:2]
        procs_running = open("/proc/loadavg").read().split()[3].split("/")[0]
        w.writerow({
            "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cpu_util_pct": cpu_util(),
            "mem_available_mb": round(m.get("MemAvailable", 0) / 1024, 1),
            "mem_used_mb": round(m.get("MemTotal", 0) / 1024 - m.get("MemFree", 0) / 1024, 1),
            "mem_cached_mb": round((m.get("Cached", 0) + m.get("SReclaimable", 0)) / 1024, 1),
            "swap_used_mb": round(m.get("SwapTotal", 0) / 1024 - m.get("SwapFree", 0) / 1024, 1),
            "load1": load1, "load5": load5,
            "vm_shim_count": shim_count(),
            "procs_running": procs_running,
        })
        f.flush()
        time.sleep(INTERVAL)
print("sampler stopped", OUT)
