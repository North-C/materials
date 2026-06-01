#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_events(paths):
    events = []
    for item in paths:
        path = Path(item)
        files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if event.get("event") == "stage_timing":
                            event["_path"] = str(file_path)
                            event["_line"] = line_number
                            events.append(event)
            except Exception as exc:
                print(f"warning: skip {file_path}: {exc}", file=sys.stderr)
    return events


def summarize(events, group_by):
    totals = defaultdict(lambda: {"count": 0, "duration_ms": 0.0, "failed": 0})
    for event in events:
        key = event.get(group_by) or "unknown"
        item = totals[key]
        item["count"] += 1
        item["duration_ms"] += float(event.get("duration_ms") or 0.0)
        if event.get("status") != "pass":
            item["failed"] += 1

    rows = []
    for key, item in totals.items():
        count = item["count"]
        duration_ms = item["duration_ms"]
        rows.append(
            {
                group_by: key,
                "count": count,
                "failed": item["failed"],
                "duration_ms": round(duration_ms, 3),
                "avg_ms": round(duration_ms / count, 3) if count else 0.0,
            }
        )
    return sorted(rows, key=lambda row: row["duration_ms"], reverse=True)


def print_table(rows, group_by):
    print(f"{group_by:36} {'count':>7} {'failed':>7} {'total_ms':>12} {'avg_ms':>10}")
    for row in rows:
        print(
            f"{str(row[group_by])[:36]:36} "
            f"{row['count']:7d} {row['failed']:7d} "
            f"{row['duration_ms']:12.3f} {row['avg_ms']:10.3f}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Summarize large-scale-text-editing stage profile JSONL files."
    )
    parser.add_argument("paths", nargs="+", help="Profile JSONL files or directories")
    parser.add_argument(
        "--group-by",
        choices=("stage", "phase", "resource_type", "resource_object"),
        default="stage",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    events = load_events(args.paths)
    rows = summarize(events, args.group_by)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        print_table(rows, args.group_by)


if __name__ == "__main__":
    main()
