#!/usr/bin/env python3
"""Read a narrow journal window and emit only allowlisted query timing metadata.

Run on the service host via stdin. Raw journal messages and SQL are never emitted.
"""
import datetime
import json
import math
import re
import statistics
import subprocess

UNIT = "cube-sandbox-cubemaster.service"
SINCE = "2026-10-29 04:39:06 UTC"
UNTIL = "2026-10-29 04:39:11 UTC"
proc = subprocess.run(
    ["journalctl", "--utc", "-u", UNIT, "--since", SINCE, "--until", UNTIL,
     "--no-pager", "-o", "json"],
    check=True, capture_output=True, text=True,
)
ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
sql = re.compile(r"\[([0-9]+(?:\.[0-9]+)?)ms\]\s*\[rows:([0-9]+|-)\].*?\bFROM\s+[`\"]?([A-Za-z0-9_]+)", re.I)
records = []
counts = {"journal_entries_read": 0, "source_record_not_found_lines": 0,
          "matched_snapshot_queries": 0, "unmatched_source_markers": 0,
          "unattributed_snapshot_query_lines": 0}
pending = None
for line in proc.stdout.splitlines():
    entry = json.loads(line)
    counts["journal_entries_read"] += 1
    message = entry.get("MESSAGE", "")
    if isinstance(message, list):
        message = bytes(message).decode("utf-8", errors="replace")
    if not isinstance(message, str):
        continue
    ts = int(entry.get("__REALTIME_TIMESTAMP", 0))
    pid = str(entry.get("_PID", ""))
    for part in ansi.sub("", message).splitlines():
        part = part.strip()
        if not part:
            continue
        source_match = re.search(r"snapshot_table\.go:(28|29)\b", part)
        marker = source_match is not None and "record not found" in part
        if marker:
            counts["source_record_not_found_lines"] += 1
            if pending is not None:
                counts["unmatched_source_markers"] += 1
            pending = (ts, pid, "snapshot_table.go:" + source_match.group(1))
        match = sql.search(part)
        if match and match.group(3) == "t_cube_snapshot":
            if pending is not None and pending[1] == pid and 0 <= ts - pending[0] <= 1000000:
                records.append({
                    "journal_time_utc": datetime.datetime.fromtimestamp(ts / 1e6, datetime.timezone.utc).isoformat(),
                    "source": pending[2], "error_kind": "record_not_found",
                    "table": "t_cube_snapshot", "sql_elapsed_ms": float(match.group(1)),
                    "rows": None if match.group(2) == "-" else int(match.group(2)),
                })
                counts["matched_snapshot_queries"] += 1
                pending = None
            else:
                counts["unattributed_snapshot_query_lines"] += 1
        elif not marker and pending is not None:
            # Require the immediately following nonempty journal line, avoiding
            # speculative correlation across interleaved requests.
            counts["unmatched_source_markers"] += 1
            pending = None
if pending is not None:
    counts["unmatched_source_markers"] += 1
values = sorted(r["sql_elapsed_ms"] for r in records)
summary = None if not values else {
    "count": len(values), "mean_ms": statistics.mean(values),
    "median_ms": statistics.median(values), "min_ms": values[0],
    "p95_nearest_rank_ms": values[math.ceil(.95 * len(values)) - 1],
    "max_ms": values[-1], "sum_ms": sum(values),
}
print(json.dumps({
    "schema_version": 1, "unit": UNIT, "window_utc": {"since": SINCE, "until": UNTIL},
    "collection_mode": "read_only_existing_journal", "counts": counts,
    "summary": summary, "samples": records,
    "scope_note": "The F1 load is 3 warmup plus 100 formal creates, but this outer journal window may also contain other queries. No sample is assigned to formal or warmup by ordering; these logs lack request identity. The matched count must not be equated with the formal sample count.",
    "timing_note": "GORM Trace captures elapsed before its own formatting/Printf. SQL elapsed includes the GORM/database call, potentially pool wait, but excludes this log's own formatting/write; it does not isolate server execution.",
    "privacy_note": "Only source line, error class, SQL elapsed, rows, table name and journal timestamp are emitted. SQL text and journal messages are discarded.",
}, indent=2))
