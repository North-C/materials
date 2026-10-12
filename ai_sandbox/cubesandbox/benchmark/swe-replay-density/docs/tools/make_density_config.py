#!/usr/bin/env python3
"""Generate inputs only; benchmark execution stays in the native bench-core CLI."""
import argparse
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", type=Path, required=True)
    ap.add_argument("--trajectory-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--api-url", required=True)
    ap.add_argument("--domain", default="cube.app")
    ap.add_argument("--instance", help="Select one instance_id; omit for the whole supplied mapping")
    ap.add_argument("--duration", type=int, default=14400)
    ap.add_argument("--action-timeout", type=int, default=300)
    ap.add_argument("--delay-scale", type=float, default=0.0)
    ap.add_argument("--create-batch", type=int, default=96)
    ap.add_argument("--monitor", action="store_true")
    args = ap.parse_args()
    if not args.name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.name):
        ap.error("--name must contain only letters, digits, underscore or hyphen")
    if (min(args.count, args.duration, args.action_timeout, args.create_batch) < 1
            or not math.isfinite(args.delay_scale) or args.delay_scale < 0):
        ap.error("counts/timeouts must be positive; delay-scale must be nonnegative")
    url = urlsplit(args.api_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        ap.error("--api-url must be an http(s) base URL without embedded credentials/query/fragment")
    lab, trajectories = args.lab.resolve(), args.trajectory_dir.resolve()
    mapping = json.loads(args.manifest.read_text())
    if not isinstance(mapping, dict) or not mapping:
        ap.error("template manifest must be a nonempty object")
    if args.instance:
        key = args.instance + ".replay.json"
        if key not in mapping:
            ap.error(f"instance is absent from mapping: {args.instance}")
        mapping = {key: mapping[key]}
    for key, value in mapping.items():
        if Path(key).name != key or not (trajectories / key).is_file():
            ap.error(f"trajectory missing or non-flat path: {key}")
        if not isinstance(value, str) or not value.startswith("tpl-"):
            ap.error(f"expected a confirmed Cube template ID for {key}")
    config_path = lab / "configs" / f"{args.name}.yaml"
    mapping_path = lab / "configs" / f"{args.name}.templates.json"
    if config_path.exists() or mapping_path.exists():
        ap.error("name already exists; use a new --name to preserve previous run inputs")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    (lab / "runtime").mkdir(parents=True, exist_ok=True)
    (lab / "inventory").mkdir(parents=True, exist_ok=True)
    config = {
        "workflow_type": "replay",
        "cubesandbox": {
            "timeout": 86400,
            "sandbox_ids_file": str(lab / "inventory" / f"{args.name}-sandbox-ids.txt"),
            "env": {"CUBE_API_URL": args.api_url, "CUBE_SANDBOX_DOMAIN": args.domain,
                    "CUBE_API_KEY": os.environ.get("CUBE_API_KEY", "")},
        },
        "sandbox": {"total_count": args.count, "detect_existing": False, "create_only": False},
        "create_batch": {"size": min(args.count, args.create_batch), "interval": 1},
        "task_batch": {"size": 5, "interval": 5},
        "replay": {
            "trajectory_dir": str(trajectories), "trajectory_glob": "*.replay.json",
            "template_manifest": str(mapping_path), "workdir": "/testbed", "env": {},
            "mode": "exec_only", "action_timeout": args.action_timeout,
            "delay_scale": args.delay_scale, "stop_on_error": False, "ready_probe": False,
        },
        "test": {
            "duration": args.duration, "stats_interval": 10, "benchmark_percent": 1.0,
            "benchmark_mode": "round_robin", "round_size": args.count,
            "round_count": 1, "round_interval": 0,
        },
        "report": {"output_dir": str(lab / "results" / args.name),
                   "filename_prefix": args.name, "format": "both"},
        "monitor": {
            # String, not YAML boolean: required by the validated 93f978f reader.
            "enabled": "true" if args.monitor else "false", "vmm": "cubesandbox",
            "interval": 2, "capture": "auto", "numa": "all", "disks": "all",
            "stress_file": str(lab / "runtime" / f"{args.name}.lock"),
            "log_dir": None, "merge_report": False, "report_timeout": 300,
            "skip_charts": True,
        },
    }
    with mapping_path.open("x", encoding="utf-8") as f:
        json.dump(dict(sorted(mapping.items())), f, indent=2)
        f.write("\n")
    # An authenticated deployment may supply CUBE_API_KEY. Never print it and
    # create the YAML with private permissions before writing any credential.
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    print(config_path)


if __name__ == "__main__":
    main()
