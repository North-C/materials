#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


def parse_time(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        return number if number > 10_000_000_000 else number * 1000
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def load_events(metrics_dir):
    events = []
    for path in sorted(Path(metrics_dir).glob("*.json")):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"warning: skip invalid metrics file {path}: {exc}", file=sys.stderr)
            continue
        if event.get("event") != "task_completion":
            continue
        finished_ms = event.get("finished_at_ms")
        if not isinstance(finished_ms, int):
            finished_ms = int(path.stat().st_mtime_ns // 1_000_000)
            event["finished_at_ms"] = finished_ms
            event.setdefault("finished_at", iso(finished_ms))
        event["_path"] = str(path)
        events.append(event)
    return events


def filter_events(events, args):
    task_id = args.task_id
    if task_id:
        events = [event for event in events if event.get("task_id") == task_id]

    until_ms = parse_time(args.until)
    since_ms = parse_time(args.since)

    if until_ms is None and args.window_seconds is not None:
        if args.anchor == "latest" and events:
            until_ms = max(event["finished_at_ms"] for event in events)
        else:
            until_ms = int(time.time() * 1000)

    if since_ms is None and args.window_seconds is not None:
        since_ms = until_ms - int(args.window_seconds * 1000)

    if since_ms is not None:
        events = [event for event in events if event["finished_at_ms"] >= since_ms]
    if until_ms is not None:
        events = [event for event in events if event["finished_at_ms"] <= until_ms]

    if events:
        start_ms = since_ms if since_ms is not None else min(event["finished_at_ms"] for event in events)
        end_ms = until_ms if until_ms is not None else max(event["finished_at_ms"] for event in events)
    else:
        now_ms = int(time.time() * 1000)
        start_ms = since_ms if since_ms is not None else now_ms
        end_ms = until_ms if until_ms is not None else now_ms

    if end_ms < start_ms:
        start_ms, end_ms = end_ms, start_ms

    return events, start_ms, end_ms


def summarize(events, start_ms, end_ms):
    completed = len(events)
    passed = sum(1 for event in events if event.get("status") == "pass")
    failed = sum(1 for event in events if event.get("status") == "fail")
    duration_seconds = max(1e-9, (end_ms - start_ms) / 1000)
    by_task = defaultdict(lambda: {"completed": 0, "passed": 0, "failed": 0})
    for event in events:
        task = event.get("task_id", "unknown")
        by_task[task]["completed"] += 1
        if event.get("status") == "pass":
            by_task[task]["passed"] += 1
        elif event.get("status") == "fail":
            by_task[task]["failed"] += 1

    return {
        "window": {
            "start": iso(start_ms),
            "end": iso(end_ms),
            "duration_seconds": duration_seconds,
        },
        "completed": completed,
        "passed": passed,
        "failed": failed,
        "throughput_per_second": completed / duration_seconds,
        "throughput_per_minute": completed * 60 / duration_seconds,
        "throughput_per_hour": completed * 3600 / duration_seconds,
        "by_task": dict(sorted(by_task.items())),
    }


def bucketize(events, start_ms, end_ms, bucket_seconds):
    if not bucket_seconds:
        return []
    bucket_ms = int(bucket_seconds * 1000)
    if bucket_ms <= 0:
        raise ValueError("--bucket-seconds must be positive")

    buckets = []
    cursor = start_ms
    while cursor < end_ms:
        bucket_end = min(cursor + bucket_ms, end_ms)
        bucket_events = [
            event for event in events
            if cursor <= event["finished_at_ms"] < bucket_end
        ]
        item = summarize(bucket_events, cursor, bucket_end)
        buckets.append(item)
        cursor = bucket_end
    return buckets


def print_table(summary, buckets):
    window = summary["window"]
    print(f"window: {window['start']} .. {window['end']} ({window['duration_seconds']:.3f}s)")
    print(
        "total: completed={completed} passed={passed} failed={failed} "
        "throughput={tpm:.3f}/min".format(
            completed=summary["completed"],
            passed=summary["passed"],
            failed=summary["failed"],
            tpm=summary["throughput_per_minute"],
        )
    )
    for task, data in summary["by_task"].items():
        print(
            f"task: {task} completed={data['completed']} "
            f"passed={data['passed']} failed={data['failed']}"
        )
    if buckets:
        print("buckets:")
        for bucket in buckets:
            print(
                "  {start} completed={completed} passed={passed} failed={failed} "
                "throughput={tpm:.3f}/min".format(
                    start=bucket["window"]["start"],
                    completed=bucket["completed"],
                    passed=bucket["passed"],
                    failed=bucket["failed"],
                    tpm=bucket["throughput_per_minute"],
                )
            )


def main():
    parser = argparse.ArgumentParser(
        description="Summarize Terminal-Bench task completion events from a host-readable metrics directory."
    )
    parser.add_argument("metrics_dir", help="Directory containing task_completion JSON files")
    parser.add_argument("--task-id", help="Filter by task_id")
    parser.add_argument("--since", help="Inclusive start time, ISO-8601 or epoch seconds/milliseconds")
    parser.add_argument("--until", help="Inclusive end time, ISO-8601 or epoch seconds/milliseconds")
    parser.add_argument("--window-seconds", type=float, help="Summarize the last N seconds")
    parser.add_argument("--anchor", choices=("now", "latest"), default="now", help="Anchor for --window-seconds")
    parser.add_argument("--bucket-seconds", type=float, help="Emit per-bucket throughput")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text table")
    args = parser.parse_args()

    events = load_events(args.metrics_dir)
    events, start_ms, end_ms = filter_events(events, args)
    summary = summarize(events, start_ms, end_ms)
    buckets = bucketize(events, start_ms, end_ms, args.bucket_seconds)

    if args.json:
        print(json.dumps({"summary": summary, "buckets": buckets}, indent=2, sort_keys=True))
    else:
        print_table(summary, buckets)


if __name__ == "__main__":
    main()
