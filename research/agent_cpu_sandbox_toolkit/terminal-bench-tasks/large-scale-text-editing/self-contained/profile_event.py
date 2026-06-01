#!/usr/bin/env python3
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def enabled():
    return bool(os.environ.get("TBENCH_PROFILE_FILE"))


def _event_base():
    return {
        "schema_version": 1,
        "event": "stage_timing",
        "task_id": os.environ.get("TBENCH_PROFILE_TASK_ID", "large-scale-text-editing"),
        "mode": os.environ.get("TBENCH_PROFILE_MODE", ""),
        "rows": int(os.environ.get("TBENCH_PROFILE_ROWS", "0") or "0"),
        "run_id": os.environ.get("TBENCH_PROFILE_RUN_ID", ""),
        "iteration": int(os.environ.get("TBENCH_PROFILE_ITERATION", "1") or "1"),
        "hostname": os.uname().nodename,
        "pid": os.getpid(),
    }


def write_stage(stage, phase, resource_type, resource_object, status, exit_code, started_ns, finished_ns):
    profile_file = os.environ.get("TBENCH_PROFILE_FILE")
    if not profile_file:
        return

    duration_ns = max(0, finished_ns - started_ns)
    event = _event_base()
    event.update(
        {
            "stage": stage,
            "phase": phase,
            "resource_type": resource_type,
            "resource_object": resource_object,
            "status": status,
            "exit_code": int(exit_code),
            "started_at_ms": started_ns // 1_000_000,
            "finished_at_ms": finished_ns // 1_000_000,
            "duration_ns": duration_ns,
            "duration_ms": round(duration_ns / 1_000_000, 3),
        }
    )

    path = Path(profile_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


@contextmanager
def stage(stage_name, phase, resource_type, resource_object):
    if not enabled():
        yield
        return

    started_ns = time.time_ns()
    status = "pass"
    exit_code = 0
    try:
        yield
    except SystemExit as exc:
        status = "fail"
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
        raise
    except Exception:
        status = "fail"
        exit_code = 1
        raise
    finally:
        write_stage(
            stage_name,
            phase,
            resource_type,
            resource_object,
            status,
            exit_code,
            started_ns,
            time.time_ns(),
        )


def main():
    if len(sys.argv) != 9:
        print(
            "usage: profile_event.py STAGE PHASE RESOURCE_TYPE RESOURCE_OBJECT STATUS EXIT_CODE STARTED_NS FINISHED_NS",
            file=sys.stderr,
        )
        return 2

    stage_name, phase, resource_type, resource_object, status, exit_code, started_ns, finished_ns = sys.argv[1:]
    write_stage(
        stage_name,
        phase,
        resource_type,
        resource_object,
        status,
        exit_code,
        int(started_ns),
        int(finished_ns),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
