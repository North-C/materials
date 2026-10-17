#!/usr/bin/env python3
"""Community-style c100/n100/-w 3 capture: warmup runs inside the formal cube-bench process.

Thin wrapper over profiler capture_100.py (912b1ba). The separate c1n3 prewarmup is
disabled (config warmup must be 0) and the formal command is invoked with -w 3, so the
3 serial warmups share the HTTP client with the formal phase. total_time_s still
excludes warmup (cube-bench starts its timer after RunWarmup). Inventory ownership is
103 instances recorded as unknown_phase; no seq->ID mapping is claimed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_100  # noqa: E402

WARMUP = "3"
_original_capture_command = capture_100.capture_command


def capture_command(config, run, binary):
    command = _original_capture_command(config, run, binary)
    index = command.index("--warmup")
    command[index + 1] = WARMUP
    # capture.py copies os.environ to the runner; the runner reads CUBE_CAPTURE_WARMUP.
    return ["env", "CUBE_CAPTURE_WARMUP=" + WARMUP] + command


def run_warmup(binary, template, count, directory, environment):
    if count != 0:
        raise ValueError("capture_w3 requires config warmup=0 (separate prewarmup disabled)")
    Path(directory).mkdir(mode=0o700)
    return 0, {"schema_version": 1, "mode": "in_process_cube_bench_w3", "count": 0,
               "status": "skipped", "separate_prewarmup": False, "client_connection_reused": True}


capture_100.capture_command = capture_command
capture_100.run_warmup = run_warmup

if __name__ == "__main__":
    raise SystemExit(capture_100.main())
